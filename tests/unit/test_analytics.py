import numpy as np
import pandas as pd

from src.analytics.anomalies import detect_anomalies
from src.analytics.correlations import compute_correlations
from src.analytics.kpi import compute_kpi
from src.analytics.seasonality import compute_seasonality
from src.analytics.service import apply_filters, build_analytics_report
from src.analytics.trends import compute_trend


def _sample_frame(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    dates = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    trend = np.linspace(100, 160, n)
    weekly = 10 * np.sin(2 * np.pi * dates.dayofweek.to_numpy() / 7)
    promo = ((dates.day.to_numpy() % 15) == 0).astype(float) * 20
    noise = rng.normal(0, 3, n)
    y = np.asarray(trend + weekly + promo + noise, dtype=float)
    spike_idx = min(50, n - 1)
    y[spike_idx] = y[spike_idx] * 3
    return pd.DataFrame(
        {
            "ds": dates,
            "y": y,
            "series_key": "total",
            "promo_flag": ((dates.day.to_numpy() % 15) == 0).astype(float),
            "marketing_spend": rng.uniform(10, 40, n) + promo,
            "dim_category": rng.choice(["A", "B"], size=n),
        }
    )


def test_kpi_basic_stats() -> None:
    frame = _sample_frame(30)
    kpi = compute_kpi(frame, frequency="D")
    assert kpi.points == 30
    assert kpi.total > 0
    assert kpi.min_date is not None


def test_trend_positive_slope() -> None:
    frame = _sample_frame(60)
    trend = compute_trend(frame, frequency="D")
    assert trend.slope_per_period > 0
    assert len(trend.rolling_mean) == 60


def test_seasonality_dow_profile() -> None:
    frame = _sample_frame(90)
    season = compute_seasonality(frame, frequency="D")
    assert len(season.by_dow) == 7
    assert season.weekly_strength is not None


def test_anomaly_detects_spike() -> None:
    frame = _sample_frame(80)
    anomalies = detect_anomalies(frame)
    assert anomalies.count >= 1


def test_correlation_requires_variability() -> None:
    frame = _sample_frame(80)
    corr = compute_correlations(frame, ["promo_flag", "marketing_spend"], max_lag=3)
    assert corr.pairs
    assert "вызывал" in corr.disclaimer or "Вместе" in corr.disclaimer


def test_constant_driver_skipped() -> None:
    frame = _sample_frame(40)
    frame["const_driver"] = 1.0
    corr = compute_correlations(frame, ["const_driver"], max_lag=2)
    assert corr.pairs == []


def test_lagged_correlation_uses_time_order() -> None:
    frame = _sample_frame(40).sort_values("ds", ascending=False).reset_index(drop=True)
    corr = compute_correlations(frame, ["marketing_spend"], max_lag=2)
    assert corr.pairs
    assert corr.pairs[0]["best_lag"] is not None


def test_filters_and_report() -> None:
    frame = _sample_frame(50)
    filtered = apply_filters(frame, series_key="total", dimension_filters={"category": "A"})
    assert not filtered.empty
    assert (filtered["dim_category"] == "A").all()
    report = build_analytics_report(filtered, frequency="D")
    assert report.kpi.points == len(filtered)
    assert isinstance(report.to_dict(), dict)
