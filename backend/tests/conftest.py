"""Database fixtures.

Tests run against real Postgres (the content rules live in triggers, constraints
and a view, which SQLite cannot emulate):

- DATABASE_URL_TEST set: a Neon *branch* (never main). Use its direct
  (non-pooled) URL. Each test session migrates into a fresh schema and drops it.
- Otherwise: a throwaway local cluster (initdb) if PostgreSQL binaries exist.
- Otherwise the DB tests are skipped.

Each test runs inside a transaction that is rolled back.
"""

from __future__ import annotations

import glob
import os
import shutil
import socket
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from vv_backend.db.session import make_engine, normalize_url

BACKEND = Path(__file__).resolve().parents[1]


def _pg_bindir() -> Path | None:
    found = shutil.which("pg_config")
    if found:
        out = subprocess.run([found, "--bindir"], capture_output=True, text=True, check=False)
        cand = Path(out.stdout.strip())
        if (cand / "initdb").exists():
            return cand
    for d in sorted(glob.glob("/usr/lib/postgresql/*/bin"), reverse=True):
        if Path(d, "initdb").exists():
            return Path(d)
    return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalPostgres:
    """initdb + pg_ctl in a temp dir. Postgres refuses to run as root, so as root
    the cluster runs as the `postgres` OS user in a directory it can access."""

    def __init__(self, bindir: Path):
        self.bindir = bindir
        self.as_root = os.geteuid() == 0
        base = "/var/tmp" if self.as_root else None
        self.dir = Path(tempfile.mkdtemp(prefix="vv-pg-test-", dir=base))
        self.port = _free_port()

    def _run(self, *args: str) -> None:
        cmd = list(args)
        if self.as_root:
            cmd = ["runuser", "-u", "postgres", "--", *cmd]
        subprocess.run(cmd, check=True, capture_output=True)

    def start(self) -> str:
        if self.as_root:
            shutil.chown(self.dir, user="postgres")
        data = self.dir / "data"
        self._run(
            str(self.bindir / "initdb"),
            "-D",
            str(data),
            "-A",
            "trust",
            "-U",
            "vv",
            "-E",
            "UTF8",
            "--locale=C.UTF-8",
        )
        self._run(
            str(self.bindir / "pg_ctl"),
            "-D",
            str(data),
            "-w",
            "-l",
            str(self.dir / "log"),
            "-o",
            f"-p {self.port} -k {self.dir} -c listen_addresses=127.0.0.1 -c fsync=off",
            "start",
        )
        return f"postgresql://vv@127.0.0.1:{self.port}/postgres"

    def stop(self) -> None:
        try:
            self._run(
                str(self.bindir / "pg_ctl"), "-D", str(self.dir / "data"), "-m", "fast", "stop"
            )
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    return cfg


def migrate(engine: Engine, revision: str = "head", down: bool = False) -> None:
    cfg = _alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        (command.downgrade if down else command.upgrade)(cfg, revision)


@pytest.fixture(scope="session")
def server_url() -> Iterator[str]:
    """URL of a server we may create databases/schemas on."""
    if os.environ.get("DATABASE_URL_TEST"):
        yield os.environ["DATABASE_URL_TEST"]
        return
    bindir = _pg_bindir()
    if bindir is None:
        pytest.skip("no DATABASE_URL_TEST and no local PostgreSQL binaries")
    pg = LocalPostgres(bindir)
    try:
        yield pg.start()
    finally:
        pg.stop()


@pytest.fixture(scope="session")
def fresh_db(server_url: str):
    """Factory: an empty, isolated database (local) or schema (Neon branch)."""
    created: list[tuple[str, str]] = []
    neon = bool(os.environ.get("DATABASE_URL_TEST"))

    def make() -> Engine:
        name = f"vv_test_{uuid.uuid4().hex[:10]}"
        admin = create_engine(normalize_url(server_url), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f"CREATE {'SCHEMA' if neon else 'DATABASE'} {name}"))
        admin.dispose()
        created.append(("schema" if neon else "database", name))
        if neon:
            sep = "&" if "?" in server_url else "?"
            return make_engine(f"{server_url}{sep}options=-csearch_path%3D{name}")
        base = server_url.rsplit("/", 1)[0]
        return make_engine(f"{base}/{name}")

    yield make
    admin = create_engine(normalize_url(server_url), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        for kind, name in created:
            if kind == "schema":
                conn.execute(text(f"DROP SCHEMA IF EXISTS {name} CASCADE"))
            else:
                conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture(scope="session")
def migrated_engine(fresh_db) -> Engine:
    engine = fresh_db()
    migrate(engine)
    return engine


@pytest.fixture
def connection(migrated_engine: Engine) -> Iterator:
    """A connection inside a transaction that is rolled back after the test."""
    conn = migrated_engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


def session_on(conn) -> Session:
    # commits inside become savepoint releases; the outer transaction still rolls back
    return Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
def session(connection) -> Iterator[Session]:
    s = session_on(connection)
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def api(connection):
    """FastAPI test client with simulated Clerk tokens, in-memory R2 and a fake scorer."""
    from .api_helpers import make_api

    return make_api(connection)
