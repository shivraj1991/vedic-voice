"""Database engine for Neon serverless Postgres.

- `NullPool`: Lambda must not hold connections; Neon's pooler (PgBouncer) does
  the pooling and lets the database scale to zero (cost guardrail).
- TLS is mandatory for anything but a local test database (SECURITY.md).
- Short connect timeout with a bounded retry covers Neon cold starts.
- No default URL: settings fail fast when DATABASE_URL is missing.
"""

from __future__ import annotations

import os
import time
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", ""}
CONNECT_TIMEOUT_S = 10


class ConfigError(RuntimeError):
    """Raised for a missing or unsafe database configuration."""


def normalize_url(url: str) -> str:
    """Neon hands out `postgresql://...`; SQLAlchemy needs the psycopg 3 driver name."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    if not url.startswith("postgresql+psycopg://"):
        raise ConfigError("database URL must be a postgresql:// URL")
    return url


def check_tls(url: str) -> None:
    """Remote databases must use sslmode=require (or stricter)."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if host in LOCAL_HOSTS or host.startswith("/"):
        return
    mode = parse_qs(parts.query).get("sslmode", [""])[0]
    if mode not in {"require", "verify-ca", "verify-full"}:
        raise ConfigError("remote database URL must include sslmode=require")


def url_from_env(var: str = "DATABASE_URL") -> str:
    url = os.environ.get(var)
    if not url:
        raise ConfigError(f"{var} is not set")
    return url


def make_engine(url: str | None = None, *, var: str = "DATABASE_URL") -> Engine:
    raw = url or url_from_env(var)
    check_tls(raw)
    return create_engine(
        normalize_url(raw),
        poolclass=NullPool,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_S, "application_name": "vedic-voice"},
    )


def wait_for_db(engine: Engine, attempts: int = 3, backoff_s: float = 1.0) -> None:
    """Bounded retry for the first connection (Neon compute may be waking up)."""
    for i in range(attempts):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError:
            if i == attempts - 1:
                raise
            time.sleep(backoff_s * 2**i)
