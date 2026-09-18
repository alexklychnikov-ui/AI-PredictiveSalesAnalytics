import os

import pytest

from src.db.session import check_db


@pytest.mark.skipif(
    os.getenv("RUN_DB_INTEGRATION") != "1",
    reason="Set RUN_DB_INTEGRATION=1 with reachable DATABASE_URL",
)
def test_database_connection() -> None:
    ok, message = check_db()
    assert ok, message
    assert "PostgreSQL" in message
