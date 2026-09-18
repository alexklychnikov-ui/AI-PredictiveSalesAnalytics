from datetime import UTC, datetime

import pytest

from src.db.repositories import DatasetRepository
from src.db.session import reset_engine, session_scope
from src.schemas import DatasetCreate, ObservationCreate


@pytest.fixture(autouse=True)
def _reset_engine() -> None:
    reset_engine()
    yield
    reset_engine()


def test_create_list_and_delete_dataset() -> None:
    payload = DatasetCreate(
        name="stage2-test",
        source_filename="demo.csv",
        frequency="D",
        target_kpi="revenue",
        column_mapping={"date": "ds", "sales": "y"},
        quality_report={"rows": 2, "status": "ok"},
        observations=[
            ObservationCreate(ds=datetime(2024, 1, 1, tzinfo=UTC), y=100.0),
            ObservationCreate(ds=datetime(2024, 1, 2, tzinfo=UTC), y=120.0),
        ],
    )

    with session_scope() as session:
        repo = DatasetRepository(session)
        created = repo.create_with_observations(payload)
        dataset_id = created.id
        assert dataset_id > 0

    with session_scope() as session:
        repo = DatasetRepository(session)
        loaded = repo.get_by_id(dataset_id)
        assert loaded is not None
        assert loaded.name == "stage2-test"
        assert len(loaded.observations) == 2
        summaries = repo.list_summaries()
        assert any(item.id == dataset_id and item.observations_count == 2 for item in summaries)

    with session_scope() as session:
        repo = DatasetRepository(session)
        assert repo.delete_by_id(dataset_id) is True

    with session_scope() as session:
        repo = DatasetRepository(session)
        assert repo.get_by_id(dataset_id) is None
