"""Check that the app role `vv_app` is least-privilege on the current database.

Run after migrations (neon-migrate workflow): `python -m vv_backend.db.check_app_role`.
Exists because a role created on the Neon console joins `neon_superuser` and can
write all data, which silently defeats the narrow grants of migration 0002.
Prints what it checked (no secrets) and exits 1 on any problem.
"""

from __future__ import annotations

import sys

from sqlalchemy import Connection, text

from .session import make_engine

APP_ROLE = "vv_app"


def problems(conn: Connection, role: str = APP_ROLE) -> list[str]:
    exists = conn.execute(
        text("SELECT rolcanlogin FROM pg_roles WHERE rolname = :r"), {"r": role}
    ).first()
    if exists is None:
        return [f"role {role} does not exist; create it with SQL (see backend/README.md)"]
    out: list[str] = []
    if conn.execute(
        text("SELECT pg_has_role(:r, 'pg_write_all_data', 'USAGE')"), {"r": role}
    ).scalar():
        out.append(f"{role} can write all data (Neon console role?); recreate it with SQL")

    def can(priv: str, table: str) -> bool:
        return bool(
            conn.execute(
                text("SELECT has_table_privilege(:r, :t, :p)"), {"r": role, "t": table, "p": priv}
            ).scalar()
        )

    must = [("SELECT", "verified_shlokas"), ("UPDATE", "shlokas"), ("INSERT", "content_audit")]
    must_not = [("UPDATE", "content_audit"), ("DELETE", "content_audit"), ("INSERT", "sources")]
    out += [f"{role} lacks {p} on {t}; re-run migration 0002" for p, t in must if not can(p, t)]
    out += [f"{role} must not have {p} on {t}" for p, t in must_not if can(p, t)]
    return out


def main() -> int:
    engine = make_engine()
    with engine.connect() as conn:
        found = problems(conn)
    engine.dispose()
    for p in found:
        print(f"FAIL: {p}")
    if not found:
        print(f"OK: {APP_ROLE} is least-privilege (no write-all; content_audit append-only)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
