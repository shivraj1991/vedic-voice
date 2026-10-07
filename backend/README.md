# backend — API, data model, migrations, seed

- `src/vv_backend/api/` — FastAPI app (Milestone 2), run on AWS Lambda via Mangum
  (`vv_backend.lambda_handler.handler`).
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

## API (Milestone 2)

| Route | Who | Notes |
|---|---|---|
| `GET /health`, `GET /shlokas`, `GET /shlokas/{slug}` | public | verified content only |
| `GET /me`, `PUT /me/consent`, `GET /me/attempts` | learner | user row created on first call (Clerk ID only) |
| `GET /shlokas/{slug}/reference-audio` | learner | signed GET (≤15 min) + word timings |
| `POST /recordings/upload-url` | learner | signed PUT to `rec/tmp/{user}/{id}.m4a` (server-chosen key) |
| `POST /score-pronunciation` | learner | own key only; HEAD size/type check; per-user hourly limit; tmp deleted, consented copy kept |
| `GET/PATCH /admin/shlokas[/{slug}]`, `PATCH /admin/word-analyses/{id}` | admin, advisor | edits reset verified, audited |
| `POST /admin/shlokas/{slug}/verify`, `POST /admin/word-analyses/{id}/verify`, `POST /admin/audio/{id}/verify` | **advisor** | |
| `POST /admin/audio/upload-url`, `POST /admin/audio`, `GET /admin/audio`, `GET /admin/audio/{id}/play-url`, `POST /admin/audio/{id}/activate` | admin, advisor | only verified references can be activated |
| `PUT /admin/word-labels`, `GET /admin/audit` | admin, advisor | ground-truth labels; audit log |

Auth: Clerk session JWT (RS256 via JWKS), checks `exp`/`nbf`, `iss`, `azp`; role from the
token's `role` claim (Clerk session-token template `"role": "{{user.public_metadata.role}}"`).

Scoring is a separate Lambda; the request/response contract is in
`src/vv_backend/api/scoring_client.py`. Until it is deployed, `/score-pronunciation`
returns 503 (and tests use `FakeScorer`). Without R2 settings, audio routes return 503.

### Simulated tokens (until Clerk is set up)

```
uv run python -m vv_backend.devtools init                       # .dev-keys/ (gitignored)
uv run python -m vv_backend.devtools token --role advisor --sub user_dev_advisor
VV_ENV=dev VV_DEV_JWKS_PATH=.dev-keys/jwks.json CLERK_ISSUER=https://dev.clerk.local \
  CLERK_AUTHORIZED_PARTIES=http://localhost:8081 DATABASE_URL=postgresql://... \
  uv run --with uvicorn uvicorn --factory vv_backend.api.app:create_app
curl -H "Authorization: Bearer $TOKEN" localhost:8000/admin/shlokas
```
`VV_DEV_JWKS_PATH` is rejected when `VV_ENV=prod`.

### Real Clerk (development instance)

Public values are in `config/clerk.dev.public.env` (issuer, JWKS URL, authorized
parties, publishable key). Run with them instead of the simulated keys:

```
set -a; . config/clerk.dev.public.env; set +a
VV_ENV=dev DATABASE_URL=postgresql://... uv run --with uvicorn uvicorn --factory vv_backend.api.app:create_app
# check a real session token (copied from the app / browser devtools):
pbpaste | uv run python -m vv_backend.devtools verify
```
Tokens from the native app carry no `azp` (no browser Origin), hence
`CLERK_ALLOW_MISSING_AZP=true`; a token that does carry `azp` must match
`CLERK_AUTHORIZED_PARTIES`.
