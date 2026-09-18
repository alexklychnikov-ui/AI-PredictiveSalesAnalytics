"""Пояснения UI для новичков."""

import pandas as pd

from src.scenarios.eligibility import profit_data_status
from src.ui.help_texts import FACTOR_HELP, PROFIT_HINT_MISSING, factor_help


def test_factor_help_covers_main_sliders() -> None:
    for code in ("discount_pct", "promo_flag", "marketing_spend", "stockout_flag"):
        text = factor_help(code)
        assert len(text) > 40
        assert code in FACTOR_HELP


def test_profit_hint_is_plain_russian() -> None:
    assert "margin_pct" in PROFIT_HINT_MISSING  # код можно упомянуть как имя колонки
    assert "прибыл" in PROFIT_HINT_MISSING.lower()
    assert "окупаем" in PROFIT_HINT_MISSING.lower()
    frame = pd.DataFrame({"ds": pd.date_range("2024-01-01", periods=40, freq="D"), "y": range(40)})
    status = profit_data_status(frame)
    assert status["available"] is False
    assert "прибыл" in status["hint"].lower()
