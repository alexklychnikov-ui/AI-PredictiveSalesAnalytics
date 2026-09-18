"""Лёгкое хранение результатов в session_state без DataFrame."""

from __future__ import annotations

from typing import Any

import pandas as pd

from src.forecasting.interface import ForecastPointOut
from src.forecasting.service import ForecastJobResult
from src.recommendations.service import InsightJobResult
from src.scenarios.service import ScenarioJobResult


def points_to_records(points: list[ForecastPointOut]) -> list[dict[str, Any]]:
    return [
        {
            "ds": str(p.ds),
            "yhat": float(p.yhat),
            "yhat_lower": None if p.yhat_lower is None else float(p.yhat_lower),
            "yhat_upper": None if p.yhat_upper is None else float(p.yhat_upper),
        }
        for p in points
    ]


def records_to_points(records: list[dict[str, Any]]) -> list[ForecastPointOut]:
    return [
        ForecastPointOut(
            ds=pd.Timestamp(r["ds"]),
            yhat=float(r["yhat"]),
            yhat_lower=None if r.get("yhat_lower") is None else float(r["yhat_lower"]),
            yhat_upper=None if r.get("yhat_upper") is None else float(r["yhat_upper"]),
        )
        for r in records
    ]


def serialize_forecast_job(
    job: ForecastJobResult,
    *,
    dataset_id: int,
    series_key: str,
) -> dict[str, Any]:
    metrics_rows = []
    for name in ("prophet", "seasonal_naive"):
        bt = job.backtests.get(name)
        if bt is None:
            continue
        m = bt.metrics
        metrics_rows.append(
            {
                "модель": name,
                "mae": m.mae,
                "rmse": m.rmse,
                "wape": m.wape,
                "smape": m.smape,
                "folds": len(bt.folds),
                "n": m.n,
                "error": bt.error,
            }
        )
    return {
        "dataset_id": dataset_id,
        "series_key": series_key,
        "quality_status": job.quality_status,
        "recommended_model": job.recommended_model,
        "selected_model": job.selected_model,
        "horizon": job.horizon,
        "history_status": job.plan.history_status,
        "max_horizon": job.plan.max_horizon,
        "notes": list(job.plan.notes),
        "unavailable_reason": job.unavailable_reason,
        "points": points_to_records(job.forecast.points),
        "metrics_rows": metrics_rows,
        "metrics_payload": job.metrics_payload,
        "config": job.config,
        "model_version": job.forecast.model_version,
        "train_start": str(job.train_start),
        "train_end": str(job.train_end),
    }


def serialize_scenario_job(
    job: ScenarioJobResult,
    *,
    dataset_id: int,
    series_key: str,
) -> dict[str, Any]:
    factor_rows = []
    for f in job.factor_scenarios:
        factor_rows.append(
            {
                "factor": f.factor,
                "scenario_value": f.scenario_value,
                "baseline_value": f.baseline_value,
                "effect_per_unit": f.effect_per_unit,
                "allowed": f.model.allowed,
                "disclaimer": f.disclaimer,
                "mae_with": f.model.mae_with,
                "mae_without": f.model.mae_without,
                "range_warning": f.range_check.get("warning"),
                "points": points_to_records(f.points) if f.model.allowed else [],
                "scenario_type": f.scenario_type,
            }
        )
    return {
        "dataset_id": dataset_id,
        "series_key": series_key,
        "base_model": job.base_model,
        "horizon": job.horizon,
        "base_total": job.base_total,
        "base_points": points_to_records(job.base_points),
        "notes": list(job.notes),
        "comparison": job.comparison_rows(),
        "stress": [
            {
                "name": s.name,
                "scenario_type": s.scenario_type,
                "pct_change": s.pct_change,
                "disclaimer": s.disclaimer,
                "points": points_to_records(s.points),
            }
            for s in job.stress
        ],
        "factors": factor_rows,
        "profit": None if job.profit is None else job.profit.to_dict(),
        "profit_status": job.profit_status,
        "eligibility": [e.to_dict() for e in job.eligibility],
        "config": job.config,
    }


def serialize_insight_job(
    job: InsightJobResult,
    *,
    dataset_id: int,
    series_key: str,
    history_start: str,
    history_end: str,
) -> dict[str, Any]:
    return {
        "dataset_id": dataset_id,
        "series_key": series_key,
        "history_start": history_start,
        "history_end": history_end,
        "source": job.source,
        "openai_model": job.openai_model,
        "notes": list(job.notes),
        "validation_ok": job.validation_ok,
        "validation_errors": list(job.validation_errors),
        "facts_hash": job.facts.get("facts_hash"),
        "facts_preview": {
            "period": job.facts.get("period"),
            "forecast": job.facts.get("forecast"),
            "scenarios": {
                "comparison": (job.facts.get("scenarios") or {}).get("comparison"),
                "eligibility": (job.facts.get("scenarios") or {}).get("eligibility"),
                "profit_status": (job.facts.get("scenarios") or {}).get("profit_status"),
            },
            "limitations": job.facts.get("limitations"),
            "facts_hash": job.facts.get("facts_hash"),
        },
        "facts_full": job.facts,
        "report": job.report.to_dict(),
    }
