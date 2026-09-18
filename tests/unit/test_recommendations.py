from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from src.recommendations.cache import cache_clear, cache_get, cache_set
from src.recommendations.facts import build_facts_payload, collect_numbers, facts_hash
from src.recommendations.rules import build_rule_recommendations
from src.recommendations.schemas import RecommendationItem, RecommendationsReport
from src.recommendations.service import run_insight_job
from src.recommendations.validate import extract_numbers_from_text, validate_report_numbers


def _frame(n: int = 90) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    t = np.arange(n)
    y = 100 + 0.2 * t + 8 * np.sin(2 * np.pi * t / 7)
    promo = ((t % 15) == 0).astype(float)
    return pd.DataFrame(
        {
            "ds": dates,
            "y": y,
            "series_key": "total",
            "promo_flag": promo,
            "marketing_spend": 40 + 20 * promo,
            "discount_pct": np.where(promo == 1, 10, 0),
        }
    )


def test_facts_hash_stable() -> None:
    payload = {"a": 1, "b": [2, 3], "facts_hash": "ignore"}
    h1 = facts_hash(payload)
    h2 = facts_hash({"b": [2, 3], "a": 1})
    assert h1 == h2


def test_build_facts_has_no_raw_rows() -> None:
    facts = build_facts_payload(_frame(60), frequency="D", horizon=7, include_prophet=False)
    assert "facts_hash" in facts
    assert "period" in facts
    assert "forecast" in facts
    blob = str(facts)
    assert "email" not in blob.lower()
    assert facts["period"]["points"] == 60


def test_rules_work_without_openai() -> None:
    facts = build_facts_payload(_frame(80), frequency="D", horizon=7, include_prophet=False)
    report = build_rule_recommendations(facts)
    assert report.recommendations
    assert report.summary


def test_validate_rejects_invented_number() -> None:
    facts = {"allowed_numbers": [10.0, 20.0], "kpi": {"total": 10.0}}
    report = RecommendationsReport(
        summary="Рост на 9999%",
        recommendations=[
            RecommendationItem(
                title="X",
                action="Y",
                evidence="база 10",
                expected_effect="9999",
                confidence="низкая",
                limitation="z",
                applicable_period="сейчас",
            )
        ],
        caveats=[],
    )
    ok, errors = validate_report_numbers(report, facts)
    assert ok is False
    assert errors


def test_validate_accepts_facts_numbers() -> None:
    facts = build_facts_payload(_frame(50), frequency="D", horizon=7, include_prophet=False)
    report = build_rule_recommendations(facts)
    ok, errors = validate_report_numbers(report, facts)
    assert ok is True, errors


def test_extract_numbers() -> None:
    assert 12.5 in extract_numbers_from_text("WAPE 12,5% и n=3")


def test_cache_roundtrip() -> None:
    cache_clear()
    cache_set("abc", {"report": {"summary": "x", "recommendations": [], "caveats": []}})
    assert cache_get("abc") is not None
    cache_clear()
    assert cache_get("abc") is None


def test_insight_job_rules_when_openai_disabled() -> None:
    cache_clear()
    job = run_insight_job(
        _frame(70),
        frequency="D",
        horizon=7,
        use_openai=False,
        include_prophet=False,
        force_refresh=True,
    )
    assert job.source == "rules"
    assert job.report.recommendations


def test_insight_job_openai_fallback_on_error() -> None:
    cache_clear()
    with patch("src.recommendations.service.openai_available", return_value=True), patch(
        "src.recommendations.service.generate_openai_report",
        side_effect=RuntimeError("boom"),
    ):
        job = run_insight_job(
            _frame(70),
            frequency="D",
            horizon=7,
            use_openai=True,
            include_prophet=False,
            force_refresh=True,
        )
    assert job.source == "openai_fallback_rules"
    assert job.report.recommendations


def test_insight_job_openai_success_mocked() -> None:
    cache_clear()
    fake = RecommendationsReport(
        summary="Кратко: точек 70",
        recommendations=[
            RecommendationItem(
                title="Мониторинг",
                action="Следить за KPI",
                evidence="точек 70",
                expected_effect="контроль",
                confidence="низкая",
                limitation="агрегаты",
                applicable_period="текущий цикл",
            )
        ],
        caveats=[],
    )
    with patch("src.recommendations.service.openai_available", return_value=True), patch(
        "src.recommendations.service.generate_openai_report",
        return_value=fake,
    ), patch("src.recommendations.service.get_settings") as gs:
        gs.return_value = MagicMock(openai_model="gpt-test")
        job = run_insight_job(
            _frame(70),
            frequency="D",
            horizon=7,
            use_openai=True,
            include_prophet=False,
            force_refresh=True,
        )
    assert job.source in {"openai", "openai_fallback_rules"}
    # 70 есть в facts → openai ok
    assert job.source == "openai"
    assert job.openai_model == "gpt-test"


def test_validate_rejects_invented_percent_even_if_small() -> None:
    facts = {"allowed_numbers": [10.0], "kpi": {"total": 10.0}}
    report = RecommendationsReport(
        summary="Рост на 15%",
        recommendations=[],
        caveats=[],
    )
    ok, errors = validate_report_numbers(report, facts)
    assert ok is False
    assert errors


def test_cache_separates_openai_flag() -> None:
    cache_clear()
    frame = _frame(70)
    job1 = run_insight_job(frame, frequency="D", horizon=7, use_openai=False, force_refresh=True)
    assert job1.source == "rules"
    with patch("src.recommendations.service.openai_available", return_value=True), patch(
        "src.recommendations.service.generate_openai_report",
        side_effect=RuntimeError("no call expected if wrongly cached"),
    ):
        job2 = run_insight_job(frame, frequency="D", horizon=7, use_openai=True, force_refresh=False)
    assert job2.source == "openai_fallback_rules"


def test_collect_numbers_from_date_strings() -> None:
    nums = collect_numbers({"period": {"start": "2023-01-01", "end": "2025-12-31"}})
    assert 2023.0 in nums
    assert 2025.0 in nums


def test_validate_allows_years_from_period() -> None:
    facts = {
        "period": {"start": "2023-01-01T00:00:00+00:00", "end": "2025-12-31T00:00:00+00:00", "points": 1096},
        "allowed_numbers": [],
    }
    facts["allowed_numbers"] = sorted(collect_numbers(facts))
    report = RecommendationsReport(
        summary="Период 2023–2025, точек 1096",
        recommendations=[],
        caveats=[],
    )
    ok, errors = validate_report_numbers(report, facts)
    assert ok is True, errors
