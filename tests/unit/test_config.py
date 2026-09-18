from src.config import Settings, get_settings


def test_settings_reject_non_postgres_url() -> None:
    try:
        Settings(DATABASE_URL="sqlite:///tmp.db")
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "postgresql" in str(exc)


def test_openai_enabled_flag() -> None:
    disabled = Settings(POSTGRES_PASSWORD="x", OPENAI_API_KEY="")
    enabled = Settings(POSTGRES_PASSWORD="x", OPENAI_API_KEY="sk-test")
    assert disabled.openai_enabled is False
    assert enabled.openai_enabled is True


def test_builds_url_encoded_password() -> None:
    settings = Settings(
        DATABASE_URL=None,
        POSTGRES_USER="sales_user",
        POSTGRES_PASSWORD="p@ss:word/1",
        POSTGRES_HOST="postgres",
        POSTGRES_DB="sales_analytics",
    )
    assert settings.database_url is not None
    assert "p%40ss%3Aword%2F1" in settings.database_url
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_get_settings_cached() -> None:
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
