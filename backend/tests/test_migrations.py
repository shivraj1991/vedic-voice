import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

from vv_backend.db.models import Base

from .conftest import migrate


def test_upgrade_downgrade_roundtrip(fresh_db):
    engine = fresh_db()
    migrate(engine)
    migrate(engine, "base", down=True)
    with engine.connect() as conn:
        assert set(inspect(conn).get_table_names()) <= {"alembic_version"}
        assert (
            conn.execute(
                text("SELECT count(*) FROM pg_views WHERE viewname = 'verified_shlokas'")
            ).scalar()
            == 0
        )
    migrate(engine)


def test_models_match_migrations(migrated_engine):
    """No schema drift: autogenerate against the migrated DB finds nothing to do."""
    with migrated_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def test_app_role_is_least_privilege(fresh_db):
    engine = fresh_db()
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'vv_app'")).scalar()
        if not exists:
            try:
                conn.execute(text("CREATE ROLE vv_app NOLOGIN"))
            except Exception:  # e.g. no CREATEROLE on a Neon branch
                pytest.skip("cannot create role vv_app here")
    migrate(engine)

    def can(priv: str, table: str) -> bool:
        with engine.connect() as conn:
            return conn.execute(
                text("SELECT has_table_privilege('vv_app', :t, :p)"), {"t": table, "p": priv}
            ).scalar()

    assert can("UPDATE", "shlokas") and can("INSERT", "attempts")
    assert can("INSERT", "content_audit") and can("SELECT", "verified_shlokas")
    assert not can("UPDATE", "content_audit") and not can("DELETE", "content_audit")
    assert not can("INSERT", "sources")
