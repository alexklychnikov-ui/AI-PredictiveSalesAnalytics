"""Адаптер Prophet за единым интерфейсом модели."""

from __future__ import annotations

import logging
from typing import Any, Literal, cast

import pandas as pd

from src.forecasting.interface import FitPredictResult, ForecastPointOut
from src.forecasting.seasonality_config import SeasonalityPlan, build_seasonality_plan

logger = logging.getLogger(__name__)


class ProphetModel:
    name = "prophet"

    def __init__(
        self,
        *,
        seasonality_mode: Literal["additive", "multiplicative"] = "additive",
        clip_negative: bool = True,
        seasonality_plan: SeasonalityPlan | None = None,
    ) -> None:
        self.seasonality_mode = seasonality_mode
        self.clip_negative = clip_negative
        self.seasonality_plan = seasonality_plan

    def fit_predict(
        self,
        history: pd.DataFrame,
        *,
        horizon: int,
        frequency: str,
    ) -> FitPredictResult:
        # Prophet тяжёлый; ленивый импорт, чтобы unit без prophet не падал на collect
        from prophet import Prophet  # noqa: PLC0415

        frame = history[["ds", "y"]].dropna().copy()
        frame["ds"] = pd.to_datetime(frame["ds"], utc=True).dt.tz_localize(None)
        frame = frame.sort_values("ds").reset_index(drop=True)
        if len(frame) < 2:
            raise ValueError("Prophet требует минимум 2 точки")
        if horizon < 1:
            raise ValueError("Горизонт должен быть >= 1")

        # Сезонности только по фактической длине train (без утечки полного ряда)
        actual_plan = build_seasonality_plan(len(frame), frequency, requested_horizon=horizon)
        weekly = actual_plan.weekly
        yearly = actual_plan.yearly
        if self.seasonality_plan is not None:
            weekly = weekly and self.seasonality_plan.weekly
            yearly = yearly and self.seasonality_plan.yearly
        clip = self.clip_negative and float(frame["y"].min()) >= 0

        model = Prophet(
            yearly_seasonality=yearly,
            weekly_seasonality=weekly if str(actual_plan.frequency).upper().startswith("D") else False,
            daily_seasonality=False,
            seasonality_mode=cast(Literal["additive", "multiplicative"], self.seasonality_mode),
        )
        logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
        model.fit(frame)

        freq = _prophet_freq(frequency)
        future = model.make_future_dataframe(periods=horizon, freq=freq, include_history=False)
        forecast = model.predict(future)

        points: list[ForecastPointOut] = []
        for _, row in forecast.iterrows():
            yhat = float(row["yhat"])
            lower = float(row["yhat_lower"]) if "yhat_lower" in row and pd.notna(row["yhat_lower"]) else None
            upper = float(row["yhat_upper"]) if "yhat_upper" in row and pd.notna(row["yhat_upper"]) else None
            if clip:
                yhat = max(0.0, yhat)
                if lower is not None:
                    lower = max(0.0, lower)
                if upper is not None:
                    upper = max(0.0, upper)
            points.append(
                ForecastPointOut(
                    ds=pd.Timestamp(row["ds"], tz="UTC"),
                    yhat=yhat,
                    yhat_lower=lower,
                    yhat_upper=upper,
                )
            )

        version = None
        try:
            import prophet as prophet_pkg

            version = getattr(prophet_pkg, "__version__", None)
        except Exception:  # noqa: BLE001
            version = None

        config: dict[str, Any] = {
            "seasonality_mode": self.seasonality_mode,
            "weekly": weekly,
            "yearly": yearly,
            "clip_negative": clip,
            "frequency": frequency,
        }
        return FitPredictResult(
            points=points,
            model_name=self.name,
            model_version=version,
            config=config,
        )


def _prophet_freq(frequency: str) -> str:
    freq = (frequency or "D").upper()
    if freq.startswith("W"):
        return "W"
    if freq.startswith("M"):
        return "MS"
    return "D"
