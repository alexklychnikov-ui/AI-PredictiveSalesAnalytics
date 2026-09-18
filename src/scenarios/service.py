"""Оркестрация сценарного моделирования."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.forecasting.interface import ForecastPointOut
from src.forecasting.service import run_forecast_job
from src.scenarios.effects import FactorScenarioResult, apply_factor_scenario
from src.scenarios.eligibility import (
    FactorEligibility,
    assess_all_factors,
    profit_data_status,
)
from src.scenarios.profit import ProfitView, estimate_profit
from src.scenarios.stress import StressScenario, build_default_stress_set


@dataclass
class ScenarioJobResult:
    base_points: list[ForecastPointOut]
    base_total: float
    base_model: str
    horizon: int
    eligibility: list[FactorEligibility]
    stress: list[StressScenario]
    factor_scenarios: list[FactorScenarioResult]
    profit: ProfitView | None
    profit_status: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    def comparison_rows(self) -> list[dict[str, Any]]:
        rows = [
            {
                "сценарий": "Базовый",
                "тип": "base",
                "сумма": self.base_total,
                "Δ к базе": 0.0,
                "Δ %": 0.0,
            }
        ]
        for s in self.stress:
            total = float(sum(p.yhat for p in s.points))
            rows.append(
                {
                    "сценарий": s.name,
                    "тип": s.scenario_type,
                    "сумма": total,
                    "Δ к базе": total - self.base_total,
                    "Δ %": (total / self.base_total - 1.0) * 100.0 if self.base_total else None,
                }
            )
        for f in self.factor_scenarios:
            if not f.model.allowed:
                continue
            total = float(sum(p.yhat for p in f.points))
            rows.append(
                {
                    "сценарий": f"Фактор {f.factor}={f.scenario_value:g}",
                    "тип": f.scenario_type,
                    "сумма": total,
                    "Δ к базе": total - self.base_total,
                    "Δ %": (total / self.base_total - 1.0) * 100.0 if self.base_total else None,
                }
            )
        return rows


def run_scenario_job(
    history: pd.DataFrame,
    *,
    frequency: str,
    horizon: int,
    optimistic_pct: float = 10.0,
    pessimistic_pct: float = -10.0,
    custom_pct: float | None = None,
    factor_values: dict[str, float] | None = None,
    model_choice: str = "auto",
    clip_negative: bool = True,
    include_prophet: bool = True,
) -> ScenarioJobResult:
    notes: list[str] = []
    forecast = run_forecast_job(
        history,
        frequency=frequency,
        horizon=horizon,
        model_choice=model_choice,
        clip_negative=clip_negative,
        include_prophet=include_prophet,
    )
    if forecast.quality_status == "unavailable" or not forecast.forecast.points:
        return ScenarioJobResult(
            base_points=[],
            base_total=0.0,
            base_model="none",
            horizon=horizon,
            eligibility=assess_all_factors(history),
            stress=[],
            factor_scenarios=[],
            profit=None,
            profit_status=profit_data_status(history),
            notes=[forecast.unavailable_reason or "Базовый прогноз недоступен"],
            config={"horizon": horizon},
        )

    base_points = forecast.forecast.points
    base_total = float(sum(p.yhat for p in base_points))
    eligibility = assess_all_factors(history)
    elig_map = {e.factor: e for e in eligibility}

    stress = build_default_stress_set(
        base_points,
        optimistic_pct=optimistic_pct,
        pessimistic_pct=pessimistic_pct,
        custom_pct=custom_pct,
        clip_negative=clip_negative,
    )

    factor_scenarios: list[FactorScenarioResult] = []
    for factor, value in (factor_values or {}).items():
        info = elig_map.get(factor)
        if info is None:
            notes.append(f"Фактор «{factor}» не найден — пропущен")
            continue
        if not info.eligible:
            notes.append(f"Фактор «{factor}» недоступен: {'; '.join(info.reasons)}")
            continue
        hist_vals = pd.to_numeric(history[factor], errors="coerce").dropna()
        last_val = float(hist_vals.iloc[-1]) if not hist_vals.empty else None
        if last_val is not None and abs(float(value) - last_val) < 1e-9 * max(1.0, abs(last_val)):
            notes.append(f"Фактор «{factor}» без изменения относительно последнего значения — пропущен")
            continue
        result = apply_factor_scenario(
            base_points,
            history,
            factor=factor,
            scenario_value=float(value),
            eligibility=info,
            clip_negative=clip_negative,
        )
        if not result.model.allowed:
            notes.append(
                f"Эффект «{factor}» не применён: {'; '.join(result.model.reasons)}"
            )
        if result.range_check.get("warning"):
            notes.append(str(result.range_check["warning"]))
        factor_scenarios.append(result)

    profit_status = profit_data_status(history)
    profit = None
    chosen = next(
        (f for f in factor_scenarios if f.model.allowed and f.factor == "marketing_spend"),
        None,
    )
    if chosen is None:
        chosen = next((f for f in factor_scenarios if f.model.allowed), None)
    if chosen is not None:
        spend_extra = 0.0
        if chosen.factor == "marketing_spend":
            spend_extra = float(chosen.scenario_value - chosen.baseline_value) * len(chosen.points)
        profit = estimate_profit(
            history, base_points, chosen.points, extra_spend=max(0.0, spend_extra)
        )
    elif stress:
        profit = estimate_profit(history, base_points, stress[0].points, extra_spend=0.0)

    return ScenarioJobResult(
        base_points=base_points,
        base_total=base_total,
        base_model=forecast.selected_model,
        horizon=forecast.horizon,
        eligibility=eligibility,
        stress=stress,
        factor_scenarios=factor_scenarios,
        profit=profit,
        profit_status=profit_status,
        notes=notes,
        config={
            "requested_horizon": horizon,
            "effective_horizon": forecast.horizon,
            "optimistic_pct": optimistic_pct,
            "pessimistic_pct": pessimistic_pct,
            "custom_pct": custom_pct,
            "factor_values": factor_values or {},
            "base_model": forecast.selected_model,
            "base_quality": forecast.quality_status,
        },
    )
