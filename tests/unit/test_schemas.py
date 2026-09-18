from datetime import UTC, datetime

from src.schemas import DatasetCreate, ObservationCreate


def test_dataset_create_schema_defaults() -> None:
    payload = DatasetCreate(
        name="demo",
        frequency="D",
        target_kpi="revenue",
        observations=[ObservationCreate(ds=datetime(2024, 1, 1, tzinfo=UTC), y=1.0)],
    )
    assert payload.status == "ready"
    assert payload.observations[0].series_key == "total"
    assert payload.column_mapping == {}
