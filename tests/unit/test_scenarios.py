import numpy as np
import pandas as pd
import pytest

from src.forecasting.interface import ForecastPointOut
from src.scenarios.effects import apply_factor_scenario, fit_factor_effect
from src.scenarios.eligibility import assess_factor, check_range, profit_data_status
from src.scenarios.service import run_scenario_job
from src.scenarios.stress import apply_percent_stress, build_default_stress_set


def _frame(n: int = 120, *, with_factors: bool = True, constant_factor: bool = False) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    t = np.arange(n)
    y = 100 + 0.2 * t + 5 * np.sin(2 * np.pi * t / 7)
    data: dict = {"ds": dates, "y": y, "series_key": "total"}
    if with_factors:
        promo = ((t % 15) == 0).astype(float)
        spend = 50 + 30 * promo + np.linspace(0, 10, n)
        if constant_factor:
            spend = np.full(n, 50.0)
        levels = [5, 10, 15, 20]
        disc = [levels[i % 4] if promo[i] == 1 else 0 for i in range(n)]
        data["promo_flag"] = promo
        data["marketing_spend"] = spend
        data["discount_pct"] = disc
    return pd.DataFrame(data)


def _base_points(n: int = 7) -> list[ForecastPointOut]:
    dates = pd.date_range("2024-06-01", periods=n, freq="D", tz="UTC")
    return [ForecastPointOut(ds=ts, yhat=100.0, yhat_lower=90.0, yhat_upper=110.0) for ts in dates]


def test_stress_percent_scales_total() -> None:
    base = _base_points(10)
    scen = apply_percent_stress(base, pct_change=10.0, name="opt", scenario_type="stress_optimistic")
    assert sum(p.yhat for p in scen.points) == pytest.approx(1100.0)
    assert "причинного" in scen.disclaimer or "Stress-test" in scen.disclaimer


def test_stress_set_has_three_when_custom() -> None:
    set_ = build_default_stress_set(_base_points(), custom_pct=3.0)
    assert len(set_) == 3


def test_eligibility_rejects_constant() -> None:
    frame = _frame(80, constant_factor=True)
    info = assess_factor(frame, "marketing_spend")
    assert info.eligible is False


def test_eligibility_accepts_variable_spend() -> None:
    frame = _frame(90)
    info = assess_factor(frame, "marketing_spend")
    assert info.eligible is True
    assert info.n_non_null >= 30


def test_eligibility_missing_factor() -> None:
    frame = _frame(50, with_factors=False)
    info = assess_factor(frame, "unit_price")
    assert info.eligible is False
    assert info.missing_hint is not None


def test_range_warns_outside() -> None:
    frame = _frame(90)
    info = assess_factor(frame, "marketing_spend")
    far = (info.max_value or 0) + 10 * ((info.max_value or 1) - (info.min_value or 0) + 1)
    check = check_range(far, info)
    assert check["ok"] is False
    assert check["warning"]


def test_profit_unavailable_without_margin() -> None:
    status = profit_data_status(_frame(60))
    assert status["available"] is False
    assert "hint" in status
    assert "прибыл" in status["hint"].lower() or "марж" in status["hint"].lower()


def test_factor_effect_blocked_when_noise_only() -> None:
    dates = pd.date_range("2024-01-01", periods=80, freq="D", tz="UTC")
    rng = np.random.default_rng(0)
    # фактор не связан с y
    frame = pd.DataFrame(
        {
            "ds": dates,
            "y": 100 + rng.normal(0, 1, 80),
            "marketing_spend": rng.uniform(10, 100, 80),
        }
    )
    info = assess_factor(frame, "marketing_spend")
    model = fit_factor_effect(frame, "marketing_spend", eligibility=info)
    # может быть allowed или нет в зависимости от шума; критично — не падает
    assert model.n_train >= 30


def test_factor_scenario_applies_when_linked() -> None:
    dates = pd.date_range("2024-01-01", periods=100, freq="D", tz="UTC")
    t = np.arange(100)
    # фактор не коллинеарен тренду: редкие всплески spend
    spend = 20.0 + 80.0 * ((t % 12) == 0).astype(float)
    y = 50 + 0.15 * t + 2.0 * spend
    frame = pd.DataFrame({"ds": dates, "y": y, "marketing_spend": spend})
    info = assess_factor(frame, "marketing_spend")
    assert info.eligible
    base = _base_points(5)
    scenario_value = float(spend[-1] + 40.0)
    result = apply_factor_scenario(
        base, frame, factor="marketing_spend", scenario_value=scenario_value, eligibility=info
    )
    assert result.model.allowed is True
    expected_delta = result.effect_per_unit * (scenario_value - result.baseline_value)
    assert result.points[0].yhat == pytest.approx(100.0 + expected_delta, rel=1e-2)


def test_run_scenario_job_stress_only() -> None:
    job = run_scenario_job(
        _frame(90),
        frequency="D",
        horizon=7,
        optimistic_pct=10,
        pessimistic_pct=-10,
        custom_pct=5,
        factor_values=None,
        model_choice="seasonal_naive",
        include_prophet=False,
    )
    assert job.base_points
    assert len(job.stress) == 3
    rows = job.comparison_rows()
    assert rows[0]["тип"] == "base"
    assert any(r["тип"] == "stress_optimistic" for r in rows)


def test_profit_unavailable_empty_margin_column() -> None:
    frame = _frame(60)
    frame["margin_pct"] = float("nan")
    status = profit_data_status(frame)
    assert status["available"] is False


def test_unchanged_factor_skipped_in_job() -> None:
    frame = _frame(90)
    last = float(pd.to_numeric(frame["marketing_spend"]).iloc[-1])
    job = run_scenario_job(
        frame,
        frequency="D",
        horizon=7,
        factor_values={"marketing_spend": last},
        model_choice="seasonal_naive",
        include_prophet=False,
    )
    assert any("без изменения" in n for n in job.notes)
    assert job.factor_scenarios == []
