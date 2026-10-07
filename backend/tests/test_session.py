import pytest

from vv_backend.db.session import ConfigError, check_tls, make_engine, normalize_url


def test_remote_urls_require_tls():
    with pytest.raises(ConfigError):
        check_tls("postgresql://u:p@ep-x.ap-southeast-1.aws.neon.tech/db")
    with pytest.raises(ConfigError):
        check_tls("postgresql://u:p@ep-x.neon.tech/db?sslmode=prefer")
    check_tls("postgresql://u:p@ep-x.neon.tech/db?sslmode=require")
    check_tls("postgresql://vv@127.0.0.1:5432/db")


def test_normalize_url():
    assert normalize_url("postgres://h/db") == "postgresql+psycopg://h/db"
    assert normalize_url("postgresql://h/db") == "postgresql+psycopg://h/db"
    with pytest.raises(ConfigError):
        normalize_url("mysql://h/db")


def test_missing_url_fails_fast(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ConfigError):
        make_engine()


def test_engine_uses_nullpool():
    from sqlalchemy.pool import NullPool

    engine = make_engine("postgresql://vv@127.0.0.1:1/db")
    assert isinstance(engine.pool, NullPool)
