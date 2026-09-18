"""Unit tests for Stage 8 export + session serialization."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.export.reports import (
    comparison_csv,
    forecast_points_csv,
    recommendations_text_report,
    scenarios_csv,
)
from src.forecasting.service import run_forecast_job
from src.ui.session_store import serialize_forecast_job


def test_forecast_csv_header() -> None:
    csv_text = forecast_points_csv(
        [{"ds": "2024-01-01", "yhat": 1.0, "yhat_lower": 0.5, "yhat_upper": 1.5}]
    )
    assert "ds,yhat,yhat_lower,yhat_upper" in csv_text
    assert "1.0" in csv_text


def test_scenarios_csv_includes_base() -> None:
    payload = {
        "base_points": [{"ds": "2024-01-02", "yhat": 10.0, "yhat_lower": None, "yhat_upper": None}],
        "stress": [
            {
                "name": "Оптимистичный",
                "scenario_type": "stress_optimistic",
                "points": [{"ds": "2024-01-02", "yhat": 11.0}],
            }
        ],
        "factors": [],
    }
    text = scenarios_csv(payload)
    assert "Базовый" in text
    assert "stress_optimistic" in text


def test_recommendations_text_contains_title() -> None:
    text = recommendations_text_report(
        {
            "source": "rules",
            "openai_model": None,
            "facts_hash": "abc",
            "notes": [],
            "report": {
                "summary": "Кратко",
                "recommendations": [
                    {
                        "title": "Мониторинг",
                        "action": "Следить",
                        "evidence": "n=10",
                        "expected_effect": "контроль",
                        "confidence": "низкая",
                        "limitation": "агрегаты",
                        "applicable_period": "сейчас",
                    }
                ],
                "caveats": ["нет margin"],
            },
        }
    )
    assert "Мониторинг" in text
    assert "Кратко" in text


def test_comparison_csv() -> None:
    rows = [{"сценарий": "Базовый", "тип": "base", "сумма": 1.0, "Δ к базе": 0.0, "Δ %": 0.0}]
    assert "Базовый" in comparison_csv(rows)


def test_serialize_forecast_has_no_dataframe() -> None:
    dates = pd.date_range("2024-01-01", periods=60, freq="D", tz="UTC")
    frame = pd.DataFrame({"ds": dates, "y": np.linspace(100, 120, 60)})
    job = run_forecast_job(frame, frequency="D", horizon=7, model_choice="seasonal_naive", include_prophet=False)
    payload = serialize_forecast_job(job, dataset_id=1, series_key="total")
    assert "points" in payload
    assert not any(isinstance(v, pd.DataFrame) for v in payload.values())
    assert payload["dataset_id"] == 1
