"""Статус качества прогноза."""

from __future__ import annotations

from src.forecasting.backtesting import ModelBacktestResult
from src.forecasting.seasonality_config import SeasonalityPlan

# коды для БД / UI mapping
QUALITY_GOOD = "good"
QUALITY_ACCEPTABLE = "acceptable"
QUALITY_LOW = "low_confidence"
QUALITY_UNAVAILABLE = "unavailable"


def resolve_quality_status(
    *,
    plan: SeasonalityPlan,
    prophet: ModelBacktestResult | None,
    baseline: ModelBacktestResult | None,
    target_wape: float | None = None,
) -> str:
    if plan.history_status == "недостаточно":
        return QUALITY_UNAVAILABLE
    if baseline is None or baseline.metrics.n == 0:
        return QUALITY_UNAVAILABLE
    if prophet is None or prophet.metrics.n == 0 or prophet.metrics.wape is None:
        return QUALITY_LOW

    base_wape = baseline.metrics.wape
    prop_wape = prophet.metrics.wape
    if base_wape is None:
        return QUALITY_LOW

    better = prop_wape <= base_wape
    within_target = target_wape is None or prop_wape <= target_wape

    if plan.history_status == "достаточно" and better and within_target:
        return QUALITY_GOOD
    if better or (within_target and plan.history_status != "недостаточно"):
        return QUALITY_ACCEPTABLE
    return QUALITY_LOW


def pick_recommended_model(
    prophet: ModelBacktestResult | None,
    baseline: ModelBacktestResult | None,
) -> str:
    if prophet is None or prophet.metrics.wape is None:
        return "seasonal_naive"
    if baseline is None or baseline.metrics.wape is None:
        return "prophet"
    if prophet.metrics.wape <= baseline.metrics.wape:
        return "prophet"
    return "seasonal_naive"
