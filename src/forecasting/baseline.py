"""Seasonal-naive baseline."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.forecasting.interface import FitPredictResult, ForecastPointOut
from src.forecasting.seasonality_config import seasonal_period_for


class SeasonalNaiveModel:
    name = "seasonal_naive"

    def __init__(self, *, clip_negative: bool = True) -> None:
        self.clip_negative = clip_negative

    def fit_predict(
        self,
        history: pd.DataFrame,
        *,
        horizon: int,
        frequency: str,
    ) -> FitPredictResult:
        frame = history[["ds", "y"]].dropna().sort_values("ds").reset_index(drop=True)
        if frame.empty:
            raise ValueError("Пустая история для baseline")
        if horizon < 1:
            raise ValueError("Горизонт должен быть >= 1")

        y = frame["y"].to_numpy(dtype=float)
        period = seasonal_period_for(frequency)
        use_seasonal = len(y) >= period + 1
        preds = np.empty(horizon, dtype=float)
        for step in range(horizon):
            if use_seasonal:
                preds[step] = y[-(period - (step % period))]
            else:
                preds[step] = y[-1]

        if self.clip_negative and float(np.nanmin(y)) >= 0:
            preds = np.maximum(preds, 0.0)

        # Простой интервал: ±1.96 * MAD остатков сезонного шага (или σ ряда)
        if use_seasonal and len(y) > period:
            resid = y[period:] - y[:-period]
            scale = float(np.median(np.abs(resid - np.median(resid)))) * 1.4826
            if not np.isfinite(scale) or scale == 0:
                scale = float(np.std(resid)) if len(resid) else 0.0
        else:
            scale = float(np.std(y)) if len(y) > 1 else 0.0
        half = 1.96 * scale if np.isfinite(scale) else 0.0

        last_ds = pd.Timestamp(frame["ds"].iloc[-1])
        freq = _pandas_freq(frequency)
        future_index = pd.date_range(last_ds, periods=horizon + 1, freq=freq)[1:]
        points = [
            ForecastPointOut(
                ds=pd.Timestamp(ts),
                yhat=float(preds[i]),
                yhat_lower=float(preds[i] - half),
                yhat_upper=float(preds[i] + half),
            )
            for i, ts in enumerate(future_index)
        ]
        config: dict[str, Any] = {
            "seasonal_period": period,
            "mode": "seasonal" if use_seasonal else "naive_last",
            "clip_negative": self.clip_negative and float(np.nanmin(y)) >= 0,
        }
        return FitPredictResult(
            points=points,
            model_name=self.name,
            model_version="1.0",
            config=config,
        )


def _pandas_freq(frequency: str) -> str:
    freq = (frequency or "D").upper()
    if freq.startswith("W"):
        return "W-MON"
    if freq.startswith("M"):
        return "MS"
    return "D"
