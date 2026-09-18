"""Stress-test сценарии (% к базовому прогнозу) — не причинный эффект."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.forecasting.interface import ForecastPointOut


@dataclass
class StressScenario:
    name: str
    scenario_type: str
    pct_change: float
    points: list[ForecastPointOut]
    disclaimer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "scenario_type": self.scenario_type,
            "pct_change": self.pct_change,
            "disclaimer": self.disclaimer,
            "points": [
                {
                    "ds": str(p.ds),
                    "yhat": p.yhat,
                    "yhat_lower": p.yhat_lower,
                    "yhat_upper": p.yhat_upper,
                }
                for p in self.points
            ],
            "total": float(sum(p.yhat for p in self.points)),
        }


_DISCLAIMER = (
    "Stress-test: процентное изменение базового прогноза, "
    "не оценка причинного эффекта фактора."
)


def apply_percent_stress(
    base_points: list[ForecastPointOut],
    *,
    pct_change: float,
    name: str,
    scenario_type: str,
    clip_negative: bool = True,
) -> StressScenario:
    factor = 1.0 + pct_change / 100.0
    points: list[ForecastPointOut] = []
    for p in base_points:
        yhat = float(p.yhat) * factor
        lower = None if p.yhat_lower is None else float(p.yhat_lower) * factor
        upper = None if p.yhat_upper is None else float(p.yhat_upper) * factor
        if clip_negative:
            yhat = max(0.0, yhat)
            if lower is not None:
                lower = max(0.0, lower)
            if upper is not None:
                upper = max(0.0, upper)
        points.append(
            ForecastPointOut(ds=pd.Timestamp(p.ds), yhat=yhat, yhat_lower=lower, yhat_upper=upper)
        )
    return StressScenario(
        name=name,
        scenario_type=scenario_type,
        pct_change=pct_change,
        points=points,
        disclaimer=_DISCLAIMER,
    )


def build_default_stress_set(
    base_points: list[ForecastPointOut],
    *,
    optimistic_pct: float = 10.0,
    pessimistic_pct: float = -10.0,
    custom_pct: float | None = None,
    clip_negative: bool = True,
) -> list[StressScenario]:
    scenarios = [
        apply_percent_stress(
            base_points,
            pct_change=optimistic_pct,
            name="Оптимистичный",
            scenario_type="stress_optimistic",
            clip_negative=clip_negative,
        ),
        apply_percent_stress(
            base_points,
            pct_change=pessimistic_pct,
            name="Пессимистичный",
            scenario_type="stress_pessimistic",
            clip_negative=clip_negative,
        ),
    ]
    if custom_pct is not None:
        scenarios.append(
            apply_percent_stress(
                base_points,
                pct_change=custom_pct,
                name="Пользовательский",
                scenario_type="stress_custom",
                clip_negative=clip_negative,
            )
        )
    return scenarios
