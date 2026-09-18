"""Rolling-origin backtesting без утечки будущего."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from src.forecasting.baseline import SeasonalNaiveModel
from src.forecasting.interface import ForecastModel
from src.forecasting.metrics import MetricSet, compute_metrics
from src.forecasting.prophet_model import ProphetModel
from src.forecasting.seasonality_config import SeasonalityPlan, seasonal_period_for


@dataclass
class FoldResult:
    cutoff_index: int
    n_train: int
    metrics: MetricSet


@dataclass
class ModelBacktestResult:
    model_name: str
    metrics: MetricSet
    folds: list[FoldResult] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "metrics": self.metrics.to_dict(),
            "folds": len(self.folds),
            "error": self.error,
        }


def _cutoffs(n: int, horizon: int, period: int) -> list[int]:
    """Индексы конца train. Holdout = [cutoff, cutoff+horizon)."""
    min_train = max(period, 2 * horizon, 14)
    if n < min_train + horizon:
        if n > horizon + 3:
            return [n - horizon]
        return []
    first = min_train
    last = n - horizon
    step = max(1, horizon)
    cuts = list(range(first, last + 1, step))
    if not cuts or cuts[-1] != last:
        cuts.append(last)
    if len(cuts) > 5:
        idx = np.linspace(0, len(cuts) - 1, 5).round().astype(int)
        cuts = [cuts[i] for i in sorted(set(idx.tolist()))]
    return cuts


def _normalize_ds(values: pd.Series | list, frequency: str) -> pd.Series:
    series = pd.to_datetime(values, utc=True)
    freq = (frequency or "D").upper()
    if freq.startswith("W"):
        return series.dt.to_period("W-MON").dt.start_time.dt.tz_localize("UTC")
    if freq.startswith("M"):
        return series.dt.to_period("M").dt.start_time.dt.tz_localize("UTC")
    return series.dt.floor("D")


def backtest_model(
    model: ForecastModel,
    history: pd.DataFrame,
    *,
    horizon: int,
    frequency: str,
) -> ModelBacktestResult:
    frame = history[["ds", "y"]].dropna().sort_values("ds").reset_index(drop=True)
    period = seasonal_period_for(frequency)
    cuts = _cutoffs(len(frame), horizon, period)
    if not cuts:
        empty = MetricSet(mae=None, rmse=None, wape=None, smape=None, n=0)
        return ModelBacktestResult(model_name=model.name, metrics=empty, error="нет сплитов")

    y_true_all: list[float] = []
    y_pred_all: list[float] = []
    folds: list[FoldResult] = []
    last_error: str | None = None

    for cutoff in cuts:
        train = frame.iloc[:cutoff]
        actual = frame.iloc[cutoff : cutoff + horizon]
        if len(actual) < horizon:
            continue
        try:
            result = model.fit_predict(train, horizon=horizon, frequency=frequency)
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            continue
        pred_df = pd.DataFrame(
            {
                "ds": [pd.Timestamp(p.ds) for p in result.points],
                "yhat": [float(p.yhat) for p in result.points],
            }
        )
        if pred_df.empty:
            continue
        pred_df["ds"] = _normalize_ds(pred_df["ds"], frequency)
        actual_cmp = actual.copy()
        actual_cmp["ds"] = _normalize_ds(actual_cmp["ds"], frequency)
        merged = actual_cmp.merge(pred_df, on="ds", how="inner")
        if merged.empty:
            last_error = "нет совпадений дат факта и прогноза"
            continue
        yt = merged["y"].to_numpy(dtype=float)
        yp = merged["yhat"].to_numpy(dtype=float)
        fold_metrics = compute_metrics(yt, yp)
        folds.append(FoldResult(cutoff_index=cutoff, n_train=len(train), metrics=fold_metrics))
        y_true_all.extend(yt.tolist())
        y_pred_all.extend(yp.tolist())

    if not y_true_all:
        return ModelBacktestResult(
            model_name=model.name,
            metrics=MetricSet(mae=None, rmse=None, wape=None, smape=None, n=0),
            folds=folds,
            error=last_error or "не удалось оценить ни один фолд",
        )
    return ModelBacktestResult(
        model_name=model.name,
        metrics=compute_metrics(y_true_all, y_pred_all),
        folds=folds,
        error=None,
    )


def run_backtests(
    history: pd.DataFrame,
    *,
    horizon: int,
    frequency: str,
    plan: SeasonalityPlan,
    clip_negative: bool = True,
    include_prophet: bool = True,
) -> dict[str, ModelBacktestResult]:
    results: dict[str, ModelBacktestResult] = {}
    baseline = SeasonalNaiveModel(clip_negative=clip_negative)
    results[baseline.name] = backtest_model(baseline, history, horizon=horizon, frequency=frequency)

    if include_prophet:
        prophet = ProphetModel(
            seasonality_mode="additive",
            clip_negative=clip_negative,
            seasonality_plan=plan,
        )
        results[prophet.name] = backtest_model(prophet, history, horizon=horizon, frequency=frequency)
    return results
