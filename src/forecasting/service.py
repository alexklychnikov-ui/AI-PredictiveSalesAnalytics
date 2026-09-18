"""Оркестрация прогнозного запуска."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from src.forecasting.backtesting import ModelBacktestResult, run_backtests
from src.forecasting.baseline import SeasonalNaiveModel
from src.forecasting.interface import FitPredictResult, ForecastModel
from src.forecasting.prophet_model import ProphetModel
from src.forecasting.quality import pick_recommended_model, resolve_quality_status
from src.forecasting.seasonality_config import SeasonalityPlan, build_seasonality_plan


@dataclass
class ForecastJobResult:
    quality_status: str
    recommended_model: str
    selected_model: str
    horizon: int
    plan: SeasonalityPlan
    backtests: dict[str, ModelBacktestResult]
    forecast: FitPredictResult
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    config: dict[str, Any] = field(default_factory=dict)
    metrics_payload: dict[str, Any] = field(default_factory=dict)
    unavailable_reason: str | None = None


def prepare_series(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame[["ds", "y"]].dropna().copy()
    out["ds"] = pd.to_datetime(out["ds"], utc=True)
    out["y"] = out["y"].astype(float)
    return out.sort_values("ds").reset_index(drop=True)


def run_forecast_job(
    history: pd.DataFrame,
    *,
    frequency: str,
    horizon: int,
    model_choice: str = "auto",
    target_wape: float | None = None,
    clip_negative: bool = True,
    include_prophet: bool = True,
) -> ForecastJobResult:
    series = prepare_series(history)
    plan = build_seasonality_plan(len(series), frequency, requested_horizon=horizon)
    effective_horizon = min(max(1, horizon), plan.max_horizon)

    if plan.history_status == "недостаточно" or effective_horizon < 1 or series.empty:
        empty = FitPredictResult(points=[], model_name="none", config={})
        return ForecastJobResult(
            quality_status="unavailable",
            recommended_model="seasonal_naive",
            selected_model="none",
            horizon=effective_horizon,
            plan=plan,
            backtests={},
            forecast=empty,
            train_start=series["ds"].iloc[0] if not series.empty else pd.Timestamp.utcnow(),
            train_end=series["ds"].iloc[-1] if not series.empty else pd.Timestamp.utcnow(),
            config={"requested_horizon": horizon, "effective_horizon": effective_horizon},
            metrics_payload={},
            unavailable_reason="Недостаточно истории для прогноза и backtesting",
        )

    # константный ряд — только baseline
    y_std = float(series["y"].std()) if len(series) > 1 else 0.0
    constant = not (y_std > 1e-12)
    run_prophet = include_prophet and not constant

    backtests = run_backtests(
        series,
        horizon=effective_horizon,
        frequency=frequency,
        plan=plan,
        clip_negative=clip_negative,
        include_prophet=run_prophet,
    )
    baseline_bt = backtests.get("seasonal_naive")
    prophet_bt = backtests.get("prophet")
    recommended = pick_recommended_model(prophet_bt, baseline_bt)
    if constant:
        recommended = "seasonal_naive"

    if model_choice == "auto":
        selected = recommended
    elif model_choice in {"prophet", "seasonal_naive"}:
        selected = model_choice
        if selected == "prophet" and not run_prophet:
            selected = "seasonal_naive"
    else:
        selected = recommended

    quality = resolve_quality_status(
        plan=plan,
        prophet=prophet_bt,
        baseline=baseline_bt,
        target_wape=target_wape,
    )
    if constant:
        quality = "low_confidence"
        plan.notes.append("Ряд почти постоянный — Prophet отключён, использован baseline")

    if selected == "prophet":
        model: ForecastModel = ProphetModel(
            seasonality_mode="additive",
            clip_negative=clip_negative,
            seasonality_plan=plan,
        )
    else:
        model = SeasonalNaiveModel(clip_negative=clip_negative)

    forecast = model.fit_predict(series, horizon=effective_horizon, frequency=frequency)

    metrics_payload = {
        "prophet": prophet_bt.to_dict() if prophet_bt else None,
        "seasonal_naive": baseline_bt.to_dict() if baseline_bt else None,
        "recommended_model": recommended,
        "selected_model": selected,
        "target_wape": target_wape,
        "constant_series": constant,
    }
    config = {
        "requested_horizon": horizon,
        "effective_horizon": effective_horizon,
        "frequency": frequency,
        "model_choice": model_choice,
        "seasonality": plan.to_dict(),
        "clip_negative": clip_negative,
        "forecast_model_config": forecast.config,
    }
    return ForecastJobResult(
        quality_status=quality,
        recommended_model=recommended,
        selected_model=selected,
        horizon=effective_horizon,
        plan=plan,
        backtests=backtests,
        forecast=forecast,
        train_start=pd.Timestamp(series["ds"].iloc[0]),
        train_end=pd.Timestamp(series["ds"].iloc[-1]),
        config=config,
        metrics_payload=metrics_payload,
    )
