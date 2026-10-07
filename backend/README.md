# backend — data model, migrations, seed (Milestone 1)

The FastAPI API arrives in Milestone 2. This package currently holds:

- `src/vv_backend/db/models.py` — SQLAlchemy models (schema in CLAUDE.md).
- `migrations/` — Alembic. `0001` creates the tables plus the DB-level content
  rules: editing verified content resets `verified` (triggers), `content_audit`
  is append-only, learners read the `verified_shlokas` view. `0002` grants the
  least-privilege app role `vv_app` (if it exists).
- `src/vv_backend/content.py` — data access: verified-only learner reads; edits
  and verification with role checks (verify = advisor only) and audit rows.
- `src/vv_backend/seed.py` — loads `data/sources.yaml` + `data/shlokas/*.yaml`.
  Inserts only what is missing and never overwrites, because the DB is the source of truth after seeding.

## Commands

```
uv sync
uv run pytest            # starts a throwaway local Postgres, or uses DATABASE_URL_TEST
uv run ruff check . && uv run ruff format --check .

# Against a Neon *branch* (never main). Use the direct (non-pooled) URL for DDL:
export DATABASE_URL_MIGRATIONS='postgresql://owner:...@ep-...-branch.../vv?sslmode=require'
uv run alembic upgrade head
DATABASE_URL="$DATABASE_URL_MIGRATIONS" uv run python -m vv_backend.seed --dry-run
DATABASE_URL="$DATABASE_URL_MIGRATIONS" uv run python -m vv_backend.seed
```

### Tests against a Neon branch

Create a branch in the Neon console, then set `DATABASE_URL_TEST` to its
**direct** connection string (`sslmode=require`). Each test run migrates into a
fresh schema `vv_test_*` and drops it afterwards. Without `DATABASE_URL_TEST`,
tests start a local PostgreSQL (`initdb`, run as the `postgres` user when
invoked as root) and skip if no PostgreSQL binaries are installed.

### Roles (SECURITY.md: least privilege)

- **Owner role** (Neon default): runs migrations and the seed (`DATABASE_URL_MIGRATIONS`).
- **`vv_app`**: used by the API and Lambdas (`DATABASE_URL`, pooled). Create it in the
  Neon console *before* running migration 0002, or re-run 0002 afterwards
  (`alembic downgrade 0001 && alembic upgrade head`). It can read and write rows,
  only append to `content_audit`, only read `sources`, and run no DDL.
