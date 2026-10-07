"""Alembic environment. Online migrations only (we always run against a live DB)."""

from __future__ import annotations

import os

from alembic import context

from vv_backend.db.models import Base
from vv_backend.db.session import ConfigError, make_engine

config = context.config


def _url() -> str:
    url = context.get_x_argument(as_dictionary=True).get("url")
    url = url or os.environ.get("DATABASE_URL_MIGRATIONS") or os.environ.get("DATABASE_URL")
    if not url:
        raise ConfigError("set DATABASE_URL_MIGRATIONS (or DATABASE_URL), or pass -x url=...")
    return url


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:  # tests pass an open connection
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = make_engine(_url())
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("offline mode is not supported; run against a database")
run_migrations_online()
