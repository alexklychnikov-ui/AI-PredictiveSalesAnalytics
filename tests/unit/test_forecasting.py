import numpy as np
import pandas as pd
import pytest

from src.forecasting.backtesting import ModelBacktestResult, _cutoffs
from src.forecasting.baseline import SeasonalNaiveModel
from src.forecasting.metrics import MetricSet, compute_metrics, mae, smape, wape
from src.forecasting.quality import pick_recommended_model, resolve_quality_status
from src.forecasting.seasonality_config import build_seasonality_plan
from src.forecasting.service import run_forecast_job


def _series(n: int = 120, *, seed: int = 0, constant: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    if constant:
        y = np.full(n, 42.0)
    else:
        trend = np.linspace(100, 140, n)
        weekly = 8 * np.sin(2 * np.pi * dates.dayofweek.to_numpy() / 7)
        y = trend + weekly + rng.normal(0, 2, n)
    return pd.DataFrame({"ds": dates, "y": y, "series_key": "total"})


def test_metrics_known_values() -> None:
    yt = [10.0, 20.0, 30.0]
    yp = [12.0, 18.0, 33.0]
    assert mae(yt, yp) == pytest.approx(7 / 3)
    assert wape(yt, yp) == pytest.approx(100.0 * 7 / 60)
    m = compute_metrics(yt, yp)
    assert m.n == 3
    assert m.smape is not None


def test_wape_undefined_on_all_zeros() -> None:
    assert wape([0.0, 0.0], [1.0, 2.0]) is None


def test_smape_handles_zeros() -> None:
    assert smape([0.0, 10.0], [0.0, 12.0]) is not None


def test_seasonality_plan_daily() -> None:
    plan = build_seasonality_plan(200, "D", requested_horizon=30)
    assert plan.weekly is True
    assert plan.yearly is False
    assert plan.max_horizon == 50
    assert plan.history_status in {"ограниченно", "достаточно", "недостаточно"}


def test_seasonality_plan_insufficient() -> None:
    plan = build_seasonality_plan(5, "D", requested_horizon=30)
    assert plan.history_status == "недостаточно"


def test_seasonal_naive_repeats_week() -> None:
    frame = _series(28, seed=1)
    model = SeasonalNaiveModel(clip_negative=True)
    result = model.fit_predict(frame, horizon=7, frequency="D")
    assert len(result.points) == 7
    expected = frame["y"].iloc[-7:].to_numpy()
    got = np.array([p.yhat for p in result.points])
    np.testing.assert_allclose(got, expected, rtol=1e-9)


def test_seasonal_naive_clips_negative() -> None:
    dates = pd.date_range("2024-01-01", periods=20, freq="D", tz="UTC")
    y = np.linspace(5, 1, 20)
    frame = pd.DataFrame({"ds": dates, "y": y})
    # force a negative via naive path with short seasonal — use enough for period
    result = SeasonalNaiveModel(clip_negative=True).fit_predict(frame, horizon=3, frequency="D")
    assert all(p.yhat >= 0 for p in result.points)


def test_cutoffs_no_leakage_window() -> None:
    cuts = _cutoffs(100, horizon=10, period=7)
    assert cuts
    assert max(cuts) == 90
    assert all(c >= 20 for c in cuts)  # min_train = max(7, 20, 14)=20


def test_quality_prophet_better() -> None:
    plan = build_seasonality_plan(200, "D", requested_horizon=14)
    prophet = ModelBacktestResult(
        model_name="prophet",
        metrics=MetricSet(mae=1.0, rmse=1.0, wape=10.0, smape=10.0, n=20),
    )
    baseline = ModelBacktestResult(
        model_name="seasonal_naive",
        metrics=MetricSet(mae=2.0, rmse=2.0, wape=20.0, smape=20.0, n=20),
    )
    assert pick_recommended_model(prophet, baseline) == "prophet"
    assert resolve_quality_status(plan=plan, prophet=prophet, baseline=baseline) in {
        "good",
        "acceptable",
        "low_confidence",
    }


def test_run_forecast_baseline_only_constant() -> None:
    job = run_forecast_job(
        _series(80, constant=True),
        frequency="D",
        horizon=7,
        model_choice="auto",
        include_prophet=True,
    )
    assert job.selected_model == "seasonal_naive"
    assert job.quality_status == "low_confidence"
    assert len(job.forecast.points) == job.horizon


def test_run_forecast_unavailable_short() -> None:
    job = run_forecast_job(_series(5), frequency="D", horizon=30, model_choice="auto")
    assert job.quality_status == "unavailable"
    assert job.forecast.points == []


def test_seasonality_plan_caps_horizon_before_status() -> None:
    # 200 точек, запрошен горизонт 100 → эффективный 50, статус не «недостаточно»
    plan = build_seasonality_plan(200, "D", requested_horizon=100)
    assert plan.max_horizon == 50
    assert plan.history_status != "недостаточно"


def test_run_forecast_caps_large_horizon() -> None:
    job = run_forecast_job(
        _series(200),
        frequency="D",
        horizon=100,
        model_choice="seasonal_naive",
        include_prophet=False,
    )
    assert job.quality_status != "unavailable"
    assert job.horizon == 50
    assert len(job.forecast.points) == 50
