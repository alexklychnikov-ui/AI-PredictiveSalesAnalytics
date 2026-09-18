"""Profit / ROI при наличии margin или cost."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.forecasting.interface import ForecastPointOut
from src.scenarios.eligibility import profit_data_status


@dataclass
class ProfitView:
    available: bool
    mode: str | None
    base_profit: float | None
    scenario_profit: float | None
    delta_profit: float | None
    roi_pct: float | None
    hint: str | None
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "mode": self.mode,
            "base_profit": self.base_profit,
            "scenario_profit": self.scenario_profit,
            "delta_profit": self.delta_profit,
            "roi_pct": self.roi_pct,
            "hint": self.hint,
            "details": self.details,
        }


def estimate_profit(
    history: pd.DataFrame,
    base_points: list[ForecastPointOut],
    scenario_points: list[ForecastPointOut],
    *,
    extra_spend: float = 0.0,
) -> ProfitView:
    status = profit_data_status(history)
    if not status.get("available"):
        return ProfitView(
            available=False,
            mode=None,
            base_profit=None,
            scenario_profit=None,
            delta_profit=None,
            roi_pct=None,
            hint=status.get("hint"),
            details=status,
        )

    mode = status["mode"]
    if mode == "margin":
        col = "margin_pct" if "margin_pct" in history.columns else "gross_margin"
        margin_series = pd.to_numeric(history[col], errors="coerce").dropna()
        if margin_series.empty:
            return ProfitView(
                available=False,
                mode=mode,
                base_profit=None,
                scenario_profit=None,
                delta_profit=None,
                roi_pct=None,
                hint=f"Колонка «{col}» пуста",
                details=status,
            )
        margin = float(margin_series.mean()) / 100.0
        if not np.isfinite(margin):
            return ProfitView(
                available=False,
                mode=mode,
                base_profit=None,
                scenario_profit=None,
                delta_profit=None,
                roi_pct=None,
                hint="Маржа нечисловая",
                details=status,
            )
        base_rev = sum(p.yhat for p in base_points)
        scen_rev = sum(p.yhat for p in scenario_points)
        base_profit = base_rev * margin
        scen_profit = scen_rev * margin - extra_spend
    else:
        # cost_price: приближение — доля margin из (price-cost)/price по истории
        price = pd.to_numeric(history["unit_price"], errors="coerce")
        cost_col = "unit_cost" if "unit_cost" in history.columns else "cost"
        cost = pd.to_numeric(history[cost_col], errors="coerce")
        pair = pd.DataFrame({"price": price, "cost": cost}).dropna()
        pair = pair[pair["price"] > 0]
        if pair.empty:
            return ProfitView(
                available=False,
                mode=mode,
                base_profit=None,
                scenario_profit=None,
                delta_profit=None,
                roi_pct=None,
                hint="Нет валидных пар price/cost",
                details=status,
            )
        margin = float(((pair["price"] - pair["cost"]) / pair["price"]).mean())
        base_rev = sum(p.yhat for p in base_points)
        scen_rev = sum(p.yhat for p in scenario_points)
        base_profit = base_rev * margin
        scen_profit = scen_rev * margin - extra_spend

    delta = scen_profit - base_profit
    roi = None
    if abs(extra_spend) > 1e-9:
        roi = float(delta / extra_spend * 100.0)

    return ProfitView(
        available=True,
        mode=mode,
        base_profit=float(base_profit),
        scenario_profit=float(scen_profit),
        delta_profit=float(delta),
        roi_pct=roi,
        hint=None,
        details={**status, "assumed_margin": margin},
    )
