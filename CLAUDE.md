# CLAUDE.md — Vedic Voice

Guidance for anyone (human or AI) working in this repo. Keep it current: update
the decisions log and milestone status whenever something changes.

## Goal

Vedic Voice is a mobile app that helps people chant Sanskrit shlokas correctly.
The user chants into their phone; the app compares the chant with a
scholar-verified reference recording, highlights words that need work with a
plain-language reason, and explains the meaning word by word.

**Current scope: Phase 1 (MVP) only.**

1. Shloka library — 10 shlokas (Gayatri first), each with Devanagari, IAST,
   word-by-word meanings, reference audio.
2. Listen — play reference audio with the text.
3. Record — tap to chant, capture audio, show a waveform.
4. Score — overall score + per-word scores + plain-language issue for weak words.
5. Meaning — each word with its meaning.
6. Progress — streak and per-word accuracy over time.
7. Admin/Advisor console — listen to and manage recordings, manage shlokas,
   advisor review/verification, per-word labelling of test recordings.
   (Added to scope by product owner, 2026-10-06.)

Out of scope: subscriptions, B2B API, social features, swara (Vedic pitch
accent) scoring in user-facing results.

## Non-negotiable content rules

- Only shlokas with `verified = true` are shown to learners. Unreviewed AI
  output never reaches learners.
- Only a user with the **advisor** role can set `verified = true`. Any edit to
  verified content resets it to `verified = false` until re-reviewed. Every
  content change is written to `content_audit`.
- Grammar (sandhi splitting, morphology) comes from deterministic rule-based
  tooling. The LLM (Claude API) only writes plain-language explanations on top;
  it is never the source of grammatical truth.
- Source texts only from open corpora: GRETIL, Digital Corpus of Sanskrit,
  TITUS, Sanskrit Wikisource. Record each source and its license in
  `data/sources.yaml` (and the `sources` table).
- Public recordings used for testing must have a recorded license
  (e.g. CC BY / CC BY-SA / CC0) and attribution.
- User recordings are used for product improvement only with explicit opt-in
  consent. Without consent they are deleted after scoring (R2 lifecycle, 24h).

## Architecture

```
Expo app (learner + role-gated admin/advisor screens)
   │  Clerk JWT                         signed PUT/GET (short-lived)
   ▼                                    ┌──────────────────────────┐
Backend API (FastAPI on AWS Lambda) ───►│ Cloudflare R2            │
   │ TLS, pooled                        │  ref/  test/  rec/tmp/   │
   ▼                                    │  rec/consented/          │
Neon Postgres (aws-ap-southeast-1)      └──────────────────────────┘
   ▲
   └── Scoring service (Lambda container image: model + ffmpeg)

Offline content pipeline (/data): corpus text → rule-based sandhi/morphology →
Claude explanations → advisor review (console) → verified → served
```

- Monorepo; modular-monolith API + one separate scoring service.
- Audio never passes through the API: app uploads directly to R2 via a signed
  URL, then calls `POST /score-pronunciation` with the object key.
- Claude is never called per learner request. Explanations are generated once
  in the content pipeline, reviewed, and stored.

## Stack

| Layer | Choice |
|---|---|
| Mobile + admin console | React Native + Expo (TypeScript), expo-router |
| Backend | Python FastAPI, AWS Lambda (Mangum), region **ap-south-1 (Mumbai)** |
| Scoring | Python library + Lambda container image, ap-south-1 |
| Database | Neon serverless Postgres, aws-ap-southeast-1 (Singapore), pooled connection string |
| Migrations | Alembic (no manual schema changes) |
| Auth | Clerk (Expo SDK; JWT verified in FastAPI via JWKS). Roles in Clerk `publicMetadata.role` exposed as a session-token claim: `admin`, `advisor` |
| Audio storage | Cloudflare R2 (S3 API), private buckets, signed URLs only |
| LLM | Claude API, offline content pipeline only |
| Python tooling | `uv` per package (`backend/`, `scoring/`, `data/`) |
| JS tooling | `npm` in `app/` |

## Repository layout

```
app/        Expo app (learner screens + role-gated admin/advisor screens)
backend/    FastAPI API, Alembic migrations, tests
scoring/    vv_scoring library, spike harness (spike/), tests
data/       sources.yaml, shlokas/*.yaml (initial seed), pipeline scripts
docs/       optional ADRs
```

Packages do not import each other's internals. `backend` depends on `scoring`
only through the scoring service's public interface.

## Cost guardrails (free tiers: Neon Free, Clerk Hobby, R2 free, AWS free tier)

- Compress recordings on device: AAC (m4a), mono, 16 kHz, ~32 kbps. Max 60 s,
  max 2 MB.
- Don't hold DB connections: SQLAlchemy `NullPool` against Neon's pooler; let
  Neon scale to zero.
- Cache Claude explanations in the DB; never regenerate verified content.
- Few DB round trips per request (Lambda in Mumbai ↔ Neon in Singapore adds
  latency to every query).
- Flag anything that adds a recurring cost in the decisions log.

Known recurring / possible costs:
- AWS Lambda + ECR storage for the scoring image (free tier expected to cover
  pilot; ECR free tier is 500 MB/month for 12 months — image may exceed it).
- Apple Developer Program $99/yr (Milestone 3).
- Claude API: one-time per word explanation (cents).
- Admin console web hosting (if used on web): Cloudflare Pages free tier.

## Security baseline (mandatory) — see SECURITY.md

- No DB or internal ports exposed; DB reached only via Neon TLS string.
- No default/hardcoded/committed credentials. Secrets in `.env` (gitignored);
  `.env.example` lists names only.
- Every route requires a valid Clerk session, except explicitly public
  read-only endpoints (list/get verified shlokas). Admin routes also require
  the `admin` or `advisor` role; verification requires `advisor`.
- Validate all inputs; limit upload size and accepted audio formats.
- Least-privilege credentials: separate R2 keys for read vs write.
- Verify SECURITY.md checklist before marking any milestone done.

## Conventions

- Python 3.12+, type hints everywhere, `ruff` for lint+format, `pytest`.
- TypeScript strict mode, ESLint + Prettier, `jest-expo`.
- Small, focused modules with docstrings explaining *why*.
- IDs: UUIDs. Timestamps: `timestamptz`, UTC.
- Tests required for: scoring functions, data access, API routes, auth/role
  checks, and the "only verified content reaches learners" rule.
- Schema changes: Alembic migration, tested on a **Neon branch** (never main).
- One milestone at a time; commit at the end of each with a clear message.
- Ask before adding paid services, new major dependencies, or changing scope.

## Run / test commands

(Filled in as each package is created.)

```
# scoring (Milestone 0)
cd scoring && uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd scoring && uv run python -m spike.fetch      # model (pinned, sha256) + Su-śrotā test split
cd scoring && uv run python -m spike.eval       # → spike/out/{summary.md,report.json,review.html}
cd scoring && uv run python -m spike.score_file --text "<IAST or Devanagari>" --reference ref.m4a attempt.m4a
cd scoring && uv run python -m spike.eval --help
# Cloud sessions: .claude/hooks/session-start.sh syncs scoring/ and data/ and fetches their
# spike data (needs huggingface.co, github.com release downloads, gretil.sub.uni-goettingen.de)

# data / content pipeline (Milestone 0b)
cd data && uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd data && uv run python -m spike.fetch --dcs   # Vidyut data, GRETIL texts, DCS gold → data/vendor/
cd data && uv run python -m spike.eval_dcs      # split/lexicon accuracy vs DCS
cd data && uv run python -m spike.draft         # draft analyses for advisor review

cd data && uv run python -m vv_content.seed_build   # regenerate data/shlokas/*.yaml (initial seed)

# backend (Milestone 1: models, migrations, seed; Milestone 2: API)
cd backend && uv sync && uv run pytest && uv run ruff check . && uv run ruff format --check .
#   tests: local throwaway Postgres, or DATABASE_URL_TEST = Neon branch (direct URL)
cd backend && uv run alembic upgrade head                 # DATABASE_URL_MIGRATIONS = Neon branch
cd backend && uv run python -m vv_backend.seed --dry-run  # then without --dry-run
cd backend && VV_LIVE_CLERK=1 uv run pytest tests/test_clerk_live.py   # needs *.clerk.accounts.dev allowed
cd backend && uv run python -m vv_backend.devtools init && uv run python -m vv_backend.devtools token --role advisor
#   simulated Clerk tokens for local dev; see backend/README.md (refused when VV_ENV=prod)

# app (Milestone 3)
cd app && npm install && npm test && npx expo start
```

## Milestones

| # | Milestone | Status |
|---|---|---|
| 0 | Pronunciation scoring spike (+ local review page to listen to test recordings) | Done (spike) — see `scoring/spike/RESULTS.md`. Open: Commons recordings (rate-limited), vowel-length accuracy, advisor labels |
| 0b | Sanskrit tooling spike (sandhi/morphology) | Done (spike) — see `data/spike/RESULTS.md`. Open: INRIA Heritage eval (Vedic forms) |
| 1 | Data model + migrations + seed (10 shlokas, verified flag, sources) | Done — 9/10 shlokas seeded (unverified); *Sarve bhavantu* awaits an open-corpus source. Migrations tested on local Postgres 16; **run once on a Neon branch** (needs `DATABASE_URL_TEST`) |
| 2 | Backend API + Clerk auth (+ admin/advisor routes) | Done with simulated tokens (56 tests). Clerk dev instance configured (`backend/config/clerk.dev.public.env`); real JWKS fetched and forged tokens rejected (`VV_LIVE_CLERK=1 pytest tests/test_clerk_live.py`). Still to check with a real sign-in: `role` claim + native `azp`. Open: R2 buckets+keys, scoring Lambda service, API Gateway throttling + deploy |
| 3 | Mobile app: sign-in → listen → record → feedback → meaning | Not started |
| 3b | Admin/Advisor console (recordings, shlokas, review, word labels) | Not started |
| 4 | Progress tracking | Not started |

Initial 10 shlokas: Gayatri (RV 3.62.10), Mahāmṛtyuñjaya (RV 7.59.12),
Asato mā (BṛU 1.3.28), Oṃ saha nāvavatu (TaitU 2.2.2), Pūrṇamadaḥ (Īśa Up),
BG 2.47, Sarve bhavantu sukhinaḥ, Guru Brahmā, Vakratuṇḍa mahākāya,
Karāgre vasate. The last four may lack a clean open-corpus source — check
Wikisource and its license.

## Future work (tracked, not in current scope)

- **Replace GRETIL as the text source** (TODO `replace-gretil` in
  `data/sources.yaml`). GRETIL is used for now, but its Ṛgveda texts (Saṃhitā
  and pada-pāṭha) are CC BY-NC-SA and its Gītā is "reference only". Before any
  paid launch or B2B API: switch to a concrete, commercially usable source
  (Sanskrit Wikisource CC BY-SA, or an advisor-verified transcription we own),
  update `sources`, and re-verify the affected shlokas.
- Find an open-corpus source for *Sarve bhavantu sukhinaḥ* (none on GRETIL or
  Sanskrit Wikisource in its standard form); seed it once recorded in `sources.yaml`.
- Evaluate the INRIA Sanskrit Heritage segmenter as a second opinion to Vidyut
  (Vedic forms) from a network that can reach sanskrit.inria.fr.

## Decisions log

| Date | Decision | Why |
|---|---|---|
| 2026-10-06 | Monorepo; modular-monolith API + separate scoring service | Small team; atomic cross-layer changes; scoring has a heavy ML runtime and is the future B2B engine |
| 2026-10-06 | AWS Lambda in ap-south-1 (Mumbai) for API and scoring | Product owner asked for India region. Scoring ships as a container image (up to 10 GB) |
| 2026-10-06 | Neon stays in aws-ap-southeast-1 (Singapore) | Neon has no India region (verify in Neon console); Singapore is closest. Cost: ~30–70 ms per DB round trip from Mumbai → keep queries per request minimal |
| 2026-10-06 | Swara not scored for learners in MVP; measured in spike only | Many learners chant in non-Vedic style |
| 2026-10-06 | Test with public, licensed recordings until advisor recordings exist | Unblocks Milestone 0 |
| 2026-10-06 | Admin/Advisor console added to scope (was out of scope) | Product owner request: listen/manage recordings and manage shlokas |
| 2026-10-06 | Console = role-gated screens in the same Expo app (phone + web) | No second codebase; roles from Clerk |
| 2026-10-06 | After seeding, the DB is the content source of truth; YAML only seeds the initial 10 | Console edits content; `content_audit` keeps history |
| 2026-10-06 | Recordings: AAC m4a mono 16 kHz ~32 kbps, ≤60 s, ≤2 MB | Free-tier storage/bandwidth; supported on iOS and Android |
| 2026-10-06 | Python deps with `uv` | Fast, lockfiles |
| 2026-10-06 | Scoring = phoneme posteriors (wav2vec2 XLSR-53 espeak, Apache-2.0) + CTC alignment + GOP over curated confusions, calibrated against the reference recording | No Sanskrit ASR needed; phones don't autocorrect mistakes; every flag maps to an explainable issue; reference calibration absorbs model blind spots (e.g. retroflexes) |
| 2026-10-06 | Run the model with onnxruntime, not PyTorch; ship the 4-bit (q4) model | Much smaller Lambda image / cold start. Spike: q4 (230 MB) ≈ fp32 (1.2 GB) accuracy. ONNX export currently third-party (pinned + sha256); re-export ourselves before production |
| 2026-10-06 | Su-śrotā dataset (IISc, CC BY 4.0) as the main scoring test set | Many consented speakers per text, incl. Guru Brahmā, BG 2.47, RV 1.1.1. Commons recordings kept in manifest (upload.wikimedia.org rate-limited the dev sandbox) |
| 2026-10-06 | GRETIL Ṛgveda e-text is CC BY-NC-SA (non-commercial) | OK for spike/free MVP; paid app or B2B API needs another source for Gayatri / Mahāmṛtyuñjaya text (see `data/sources.yaml`) |
| 2026-10-06 | Single dropped sounds are down-weighted; "word missing" only when clearly worse than the reference | Spike: CTC model skips short vowels even in good recitations; raw deletion flags caused ~40% false flags on clean audio |
| 2026-10-07 | Grammar pipeline: split from corpus pada-pāṭha when available, else Vidyut (conservative); morphology = all Vidyut lexicon readings as candidates; advisor picks or enters | Spike vs DCS: 20% of sentences split exactly, 87% of noun readings among candidates, 65% top-1 → usable as proposals only |
| 2026-10-07 | Vidyut (MIT) approved as content-pipeline dependency | Product owner approval; offline only, never per learner request |
| 2026-10-07 | Proceed with GRETIL texts for now; replace with a concrete commercially usable source later (see Future work) | Product owner decision; unblocks Milestone 1 seed |
| 2026-10-07 | Recommended tooling: Vidyut primary + INRIA Heritage as second opinion; ByT5-Sanskrit (neural) not used for content | Comparison in `data/spike/RESULTS.md`; neural tagger conflicts with the rule-based grammar rule |
| 2026-10-07 | Console must group/search analysis candidates and allow free entry | Up to 76 readings per common word; Vedic forms (dhīmahi, pracodayāt) unknown to the lexicon |
| 2026-10-07 | Content rules enforced in the DB too: triggers reset `verified` on edits (word edits reset the shloka; derived `expected_phonemes` does not), CHECK verified ⇒ verified_by/at, `content_audit` append-only, learners read `verified_shlokas` | Defense in depth: no code path can forget the rule; role checks + audit stay in `vv_backend.content` (DB cannot see Clerk roles) |
| 2026-10-07 | Seed never overwrites existing shlokas; sources upserted by key | DB is source of truth after seeding |
| 2026-10-07 | Source wording is never silently corrected; typos/variants go to `review_notes` (e.g. Wikisource *kurū*, *guravai*) | Advisor decides; keeps provenance honest |
| 2026-10-07 | App DB role `vv_app` (row access only; content_audit insert-only; no DDL); migrations/seed use the owner role | SECURITY.md least privilege |
| 2026-10-07 | API auth: PyJWT verifies Clerk RS256 tokens via JWKS (iss, azp, exp/nbf); role only from the token `role` claim; unknown role = learner | SECURITY.md; no Clerk SDK needed server-side |
| 2026-10-07 | Clerk dev instance `exciting-man-4331.clerk.accounts.dev`; public config committed in `backend/config/clerk.dev.public.env` (no secrets; the API does not need `sk_...`) | Issuer/JWKS/publishable key are public by design |
| 2026-10-07 | Tokens without `azp` accepted only when `CLERK_ALLOW_MISSING_AZP=true`; a present `azp` must always match | Clerk omits `azp` when there is no browser Origin (native iOS/Android app) |
| 2026-10-07 | Simulated Clerk tokens (`vv_backend.devtools`, local JWKS) for dev/tests; refused when VV_ENV=prod | Build/test Milestone 2 before the Clerk app exists |
| 2026-10-07 | Rate limits: DB-backed attempts/hour per user for scoring (holds across Lambdas); per-process limiter for upload URLs; API Gateway throttling as the global ceiling (deploy) | Lambda has no shared memory; avoid adding Redis (recurring cost) |
| 2026-10-07 | Scoring called via `lambda.invoke` (IAM only) with a JSON contract in `scoring_client.py`; tmp recording deleted after scoring, copied to `rec/consented/` only with consent | Scoring not publicly invokable; privacy rule |
| 2026-10-07 | Active reference recording must be advisor-verified; low match (< 0.88) returns "couldn't match your chant" instead of word feedback | Reference is content; spike threshold |
| 2026-10-07 | Tests run on real Postgres (local throwaway cluster or Neon branch via `DATABASE_URL_TEST`), not SQLite | Triggers/view/constraints are part of the rules under test |

## Schema (implemented in Milestone 1; source of truth: `backend/src/vv_backend/db/models.py`)

Additions to the draft below: `sources.key` (id from sources.yaml) and `sources.kind`;
`word_analyses.verified_by/verified_at/created_at/updated_at`; `word_analyses.position`
orders padas within a recited word; `morphology` holds `{split_source, members, status,
proposed, candidates}` from the rule-based pipeline.

```
sources            id, name, url, license, license_url, retrieved_at, notes
shlokas            id, slug UNIQUE, title, devanagari, iast, translation,
                   source_id, source_ref, verified DEFAULT false,
                   verified_by, verified_at, review_notes, created_at, updated_at
shloka_words       id, shloka_id, position, surface_iast, surface_devanagari,
                   expected_phonemes, UNIQUE(shloka_id, position)
word_analyses      id, shloka_word_id, position, pada_iast, lemma, morphology jsonb,
                   analysis_tool, analysis_tool_version, meaning, explanation,
                   explanation_model, explanation_prompt_version, verified
audio_assets       id, shloka_id, kind (reference|test|user_consented), r2_key,
                   source_url, license, attribution, reciter, duration_ms, codec,
                   sample_rate, sha256, is_active_reference, verified, created_at
audio_word_marks   audio_asset_id, shloka_word_id, start_ms, end_ms   -- word timings
word_labels        audio_asset_id, shloka_word_id, ok, issue_code, note,
                   labeled_by, labeled_at   -- advisor ground truth for scoring eval
users              id, clerk_user_id UNIQUE, timezone, recording_consent,
                   consent_version, consent_at, created_at   -- no email/name
attempts           id, user_id, shloka_id, reference_audio_id, recording_r2_key NULL,
                   overall_score, scorer_version, duration_ms, created_at
attempt_word_scores attempt_id, shloka_word_id, score, issue_code, issue_text
content_audit      id, actor_clerk_id, entity, entity_id, action, diff jsonb, at
VIEW verified_shlokas = shlokas WHERE verified
```
