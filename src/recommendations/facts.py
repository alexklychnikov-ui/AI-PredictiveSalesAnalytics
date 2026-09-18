"""Сборка facts payload — только агрегаты, без сырых ПДн."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import pandas as pd

from src.analytics.service import build_analytics_report
from src.forecasting.service import run_forecast_job
from src.scenarios.service import run_scenario_job
from src.security.sanitize import sanitize_mapping, sanitize_tree

FORBIDDEN_FACT_KEYS = {
    "email",
    "phone",
    "client",
    "customer",
    "order_id",
    "name",
    "fio",
    "address",
}


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def to_jsonable(payload: Any) -> Any:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


def facts_hash(payload: dict[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k != "facts_hash"}
    return hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()


def _strip_forbidden(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: _strip_forbidden(v)
            for k, v in obj.items()
            if str(k).lower() not in FORBIDDEN_FACT_KEYS
            and not any(bad in str(k).lower() for bad in ("email", "phone", "order_id"))
        }
    if isinstance(obj, list):
        return [_strip_forbidden(x) for x in obj[:50]]
    return obj


def collect_numbers(obj: Any, out: set[float] | None = None) -> set[float]:
    if out is None:
        out = set()
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.add(float(obj))
        return out
    if isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
        return out
    if isinstance(obj, list):
        for v in obj:
            collect_numbers(v, out)
        return out
    if isinstance(obj, str):
        # годы/числа из дат и коротких строк агрегатов (2023-01-01 → 2023, 1, 1)
        for raw in re.findall(r"[-+]?\d+(?:[.,]\d+)?", obj):
            try:
                out.add(float(raw.replace(",", ".")))
            except ValueError:
                continue
        return out
    return out


def build_facts_payload(
    history: pd.DataFrame,
    *,
    frequency: str,
    horizon: int = 14,
    dataset_meta: dict[str, Any] | None = None,
    include_prophet: bool = False,
) -> dict[str, Any]:
    frame = history.copy()
    n = len(frame)
    period = {
        "points": n,
        "start": str(pd.to_datetime(frame["ds"]).min()) if n else None,
        "end": str(pd.to_datetime(frame["ds"]).max()) if n else None,
        "frequency": frequency,
    }

    analytics = build_analytics_report(frame, frequency=frequency).to_dict()
    # урезаем объём: без полных rolling рядов в prompt
    if "trend" in analytics and isinstance(analytics["trend"], dict):
        analytics["trend"].pop("rolling_mean", None)
    if "anomalies" in analytics and isinstance(analytics["anomalies"], dict):
        points = analytics["anomalies"].get("points") or []
        analytics["anomalies"]["points"] = points[:10]
        analytics["anomalies"]["points_truncated"] = max(0, len(points) - 10)

    forecast = run_forecast_job(
        frame,
        frequency=frequency,
        horizon=horizon,
        model_choice="auto",
        include_prophet=include_prophet,
    )
    forecast_facts = {
        "quality_status": forecast.quality_status,
        "selected_model": forecast.selected_model,
        "recommended_model": forecast.recommended_model,
        "horizon": forecast.horizon,
        "history_status": forecast.plan.history_status,
        "metrics": forecast.metrics_payload,
        "forecast_total": float(sum(p.yhat for p in forecast.forecast.points)) if forecast.forecast.points else None,
        "forecast_mean": (
            float(sum(p.yhat for p in forecast.forecast.points) / len(forecast.forecast.points))
            if forecast.forecast.points
            else None
        ),
        "notes": forecast.plan.notes[:8],
    }

    scenarios = run_scenario_job(
        frame,
        frequency=frequency,
        horizon=min(horizon, forecast.horizon or horizon),
        optimistic_pct=10.0,
        pessimistic_pct=-10.0,
        custom_pct=5.0,
        factor_values=None,
        model_choice="seasonal_naive",
        include_prophet=False,
    )
    scenario_facts = {
        "comparison": scenarios.comparison_rows(),
        "eligibility": [
            {
                "factor": e.factor,
                "eligible": e.eligible,
                "n_non_null": e.n_non_null,
                "n_unique": e.n_unique,
                "confidence": e.confidence,
                "reasons": e.reasons[:3],
            }
            for e in scenarios.eligibility
        ],
        "profit_status": scenarios.profit_status,
        "stress_disclaimer": (
            scenarios.stress[0].disclaimer if scenarios.stress else None
        ),
    }

    safe_meta = sanitize_mapping(dataset_meta or {})
    payload: dict[str, Any] = {
        "dataset": _strip_forbidden(safe_meta),
        "period": period,
        "analytics": _strip_forbidden(analytics),
        "forecast": _strip_forbidden(forecast_facts),
        "scenarios": _strip_forbidden(scenario_facts),
        "limitations": [
            "Факты — агрегаты; сырые строки и ПДн не передаются.",
            "Корреляция и регрессия факторов не доказывают причинность.",
            "Stress-test в процентах — не прогноз причинного эффекта.",
        ],
    }
    payload = sanitize_tree(payload)
    if not isinstance(payload, dict):
        raise TypeError("facts payload must be dict")
    payload["facts_hash"] = facts_hash(payload)
    payload["allowed_numbers"] = sorted(collect_numbers(payload))
    return payload
