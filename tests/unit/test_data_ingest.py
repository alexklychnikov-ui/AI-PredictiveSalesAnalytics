from datetime import UTC, datetime

import pandas as pd

from src.data.history import assess_history, clamp_horizon
from src.data.loader import load_table_from_bytes
from src.data.mapper import ColumnMapping, suggest_mapping
from src.data.pipeline import preview_ingest, to_dataset_create
from src.data.transformer import normalize_frame


def test_suggest_mapping_aliases() -> None:
    mapping = suggest_mapping(["Date", "Revenue", "promo_flag", "discount"])
    assert mapping.date_column == "Date"
    assert mapping.target_column == "Revenue"
    assert mapping.optional_columns["promo_flag"] == "promo_flag"
    assert mapping.optional_columns["discount_pct"] == "discount"


def test_loader_csv_semicolon_cp1251() -> None:
    raw = "дата;продажи\n01.01.2024;10\n02.01.2024;12\n".encode("cp1251")
    loaded = load_table_from_bytes(raw, "sales.csv")
    assert loaded.frame.shape == (2, 2)
    assert loaded.encoding == "cp1251"


def test_normalize_duplicates_and_missing_zero_fill() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01", "2024-01-03"],
            "sales": [10, 5, 7],
        }
    )
    mapping = ColumnMapping(date_column="date", target_column="sales")
    result = normalize_frame(frame, mapping, frequency="D", agg="sum", fill_missing_as_zero=True)
    assert result.missing_periods == 1
    assert len(result.clean) == 3
    day1 = result.clean.loc[result.clean["ds"] == pd.Timestamp("2024-01-01", tz="UTC"), "y"].iloc[0]
    assert day1 == 15
    day2 = result.clean.loc[result.clean["ds"] == pd.Timestamp("2024-01-02", tz="UTC"), "y"].iloc[0]
    assert day2 == 0


def test_normalize_keeps_gap_without_fill() -> None:
    frame = pd.DataFrame({"date": ["2024-01-01", "2024-01-03"], "sales": [1, 2]})
    mapping = ColumnMapping(date_column="date", target_column="sales")
    result = normalize_frame(frame, mapping, frequency="D", agg="sum", fill_missing_as_zero=False)
    assert result.missing_periods == 1
    assert len(result.clean) == 2


def test_bad_dates_and_targets_counted() -> None:
    frame = pd.DataFrame({"date": ["2024-01-01", "not-a-date"], "sales": [3, "x"]})
    mapping = ColumnMapping(date_column="date", target_column="sales")
    result = normalize_frame(frame, mapping, frequency="D", agg="sum", fill_missing_as_zero=False)
    assert result.audited["_date_error"].sum() == 1
    assert result.audited["_target_error"].sum() == 1
    assert len(result.clean) == 1


def test_history_assessment_and_horizon_clamp() -> None:
    short = assess_history(30, frequency="D", horizon=30)
    assert short.status == "недостаточно"
    assert clamp_horizon(30, frequency="D", horizon=30) == 7

    enough = assess_history(800, frequency="D", horizon=30)
    assert enough.status in {"достаточно", "ограниченно"}
    assert enough.allowed_horizon == 30


def test_constant_series_blocks_forecast_flag() -> None:
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=40, freq="D").astype(str),
            "sales": [5] * 40,
        }
    )
    mapping = ColumnMapping(date_column="date", target_column="sales")
    preview = preview_ingest(
        frame,
        source_name="const.csv",
        mapping=mapping,
        frequency="D",
        agg="sum",
        horizon=7,
        fill_missing_as_zero=False,
    )
    assert preview.quality.constant_series is True
    assert preview.quality.can_forecast is False


def test_count_aggregation_sums_events() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-01", "2024-01-02"],
            "sales": [10, 5, 7],
        }
    )
    mapping = ColumnMapping(date_column="date", target_column="sales")
    daily = normalize_frame(frame, mapping, frequency="D", agg="count", fill_missing_as_zero=False)
    assert daily.clean.loc[daily.clean["ds"] == pd.Timestamp("2024-01-01", tz="UTC"), "y"].iloc[0] == 2
    weekly = normalize_frame(frame, mapping, frequency="W", agg="count", fill_missing_as_zero=False)
    assert weekly.clean["y"].sum() == 3


def test_optional_category_skips_nan_driver() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "sales": [1, 2],
            "category": ["A", None],
        }
    )
    mapping = ColumnMapping(
        date_column="date",
        target_column="sales",
        optional_columns={"category": "category"},
    )
    result = normalize_frame(frame, mapping, frequency="D", agg="sum", fill_missing_as_zero=False)
    drivers = list(result.clean["drivers"])
    assert drivers[0].get("category") == "A"
    assert "category" not in drivers[1]


def test_to_dataset_create_observations() -> None:
    frame = pd.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "revenue": [10, 11, 12],
            "promo_flag": [0, 1, 0],
        }
    )
    mapping = suggest_mapping(list(frame.columns))
    preview = preview_ingest(
        frame,
        source_name="mini.csv",
        mapping=mapping,
        frequency="D",
        agg="sum",
        horizon=1,
        fill_missing_as_zero=False,
    )
    payload = to_dataset_create(preview, name="mini", target_kpi="revenue", frequency="D")
    assert len(payload.observations) == 3
    assert payload.observations[0].ds.replace(tzinfo=UTC) >= datetime(2024, 1, 1, tzinfo=UTC)
