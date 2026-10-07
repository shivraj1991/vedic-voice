"""least-privilege grants for the application role

The API/Lambda connects as `vv_app` (create it in the Neon console; it must
not own the schema). Migrations run as the owner role via
DATABASE_URL_MIGRATIONS. If `vv_app` does not exist yet (local dev), this
migration is a no-op; re-run `alembic downgrade 0001 && alembic upgrade head`
after creating it.

vv_app may read and write rows, but:
- no DDL (it owns nothing),
- content_audit: INSERT/SELECT only (append-only, also enforced by trigger),
- sources: SELECT only (managed by the seed/migration role).

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vv_app"
READ_WRITE = [
    "shlokas", "shloka_words", "word_analyses", "audio_assets", "audio_word_marks",
    "word_labels", "users", "attempts", "attempt_word_scores",
]  # fmt: skip


def _if_role(sql: str) -> str:
    return f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            {sql}
        END IF;
    END $$
    """


def upgrade() -> None:
    tables = ", ".join(READ_WRITE)
    op.execute(
        _if_role(f"""
        EXECUTE 'GRANT USAGE ON SCHEMA ' || quote_ident(current_schema()) || ' TO {APP_ROLE}';
        GRANT SELECT, INSERT, UPDATE, DELETE ON {tables} TO {APP_ROLE};
        GRANT SELECT, INSERT ON content_audit TO {APP_ROLE};
        GRANT USAGE ON SEQUENCE content_audit_id_seq TO {APP_ROLE};
        GRANT SELECT ON sources, verified_shlokas TO {APP_ROLE};
    """)
    )


def downgrade() -> None:
    tables = ", ".join([*READ_WRITE, "content_audit", "sources", "verified_shlokas"])
    op.execute(
        _if_role(f"""
        REVOKE ALL ON {tables} FROM {APP_ROLE};
        REVOKE ALL ON SEQUENCE content_audit_id_seq FROM {APP_ROLE};
        EXECUTE 'REVOKE USAGE ON SCHEMA ' || quote_ident(current_schema()) || ' FROM {APP_ROLE}';
    """)
    )
