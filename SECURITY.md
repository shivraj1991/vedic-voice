# SECURITY.md — Vedic Voice security checklist

Verify every applicable item before marking a milestone done. Record the result
in the milestone's commit message or report (✅ pass / ⚠️ accepted risk / N/A).

## Secrets and credentials
- [ ] No credentials, tokens, or connection strings in the repo (run a secret
      scan, e.g. `git grep -nIE "(sk-|AKIA|postgres(ql)?://[^ ]*:[^ ]*@|BEGIN .*PRIVATE KEY)"`).
- [ ] `.env` is gitignored; `.env.example` lists variable names only, no values.
- [ ] No default or fallback secrets in code (settings fail fast if missing).
- [ ] Production secrets live in AWS (Lambda env via SSM/Secrets Manager), not in files.

## Database (Neon)
- [ ] Reached only via Neon's TLS connection string (`sslmode=require`).
- [ ] Pooled connection string used by serverless code; `NullPool` in SQLAlchemy.
- [ ] Connect timeout + bounded retries configured (cold start handling).
- [ ] App role has only the privileges it needs (no superuser; migrations use a
      separate role).
- [ ] Schema changes go through Alembic and were tested on a Neon branch, not main.

## Auth and authorization (Clerk)
- [ ] Every route requires a valid Clerk session JWT, except the explicit public
      allowlist: `GET /shlokas`, `GET /shlokas/{slug}` (verified content only).
- [ ] JWT checks: signature (JWKS), `exp`/`nbf`, `iss`, and authorized party (`azp`).
- [ ] Admin routes require role `admin` or `advisor`; setting `verified = true`
      requires `advisor`. Roles come from the verified token, never from the request body.
- [ ] Tests cover: missing token, expired token, wrong issuer, wrong role.
- [ ] Learner endpoints never return unverified content (test asserts it).

## Storage (Cloudflare R2)
- [ ] No bucket is public; all access via short-lived signed URLs (≤ 15 min).
- [ ] Separate prefixes/buckets: reference/test audio vs user recordings.
- [ ] Separate R2 keys: read-only key for serving, write key scoped to the upload prefix.
- [ ] Signed upload URLs are bound to a server-generated key (user cannot pick the path).
- [ ] Lifecycle rule deletes `rec/tmp/` after 24 h; only consented recordings are kept.

## Input validation
- [ ] All request bodies/params validated with Pydantic (types, lengths, enums).
- [ ] Uploads: allowed formats AAC/m4a (and Opus/ogg if enabled); ≤ 2 MB; ≤ 60 s.
      Checked server-side (HEAD size + ffprobe) before scoring; violations deleted.
- [ ] Audio decoding runs with time and memory limits in the scoring service.
- [ ] Admin text edits are length-limited and stored as plain text (no HTML rendering).

## Network and infrastructure
- [ ] No DB or internal service ports exposed publicly.
- [ ] Scoring service is not publicly invokable (invoked by the API with IAM only).
- [ ] CORS restricted to known origins (admin web console), not `*`.
- [ ] Rate limiting on scoring and upload-URL endpoints.

## Privacy
- [ ] Recording consent is explicit opt-in, versioned, and revocable.
- [ ] Without consent, recordings are deleted after scoring.
- [ ] No email/name stored in our DB; Clerk user ID only.
- [ ] Logs contain no tokens, signed URLs, or audio content.

## Dependencies
- [ ] Dependencies pinned via lockfiles (`uv.lock`, `package-lock.json`).
- [ ] Licenses of models, datasets, recordings, and corpora recorded.
