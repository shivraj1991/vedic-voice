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
cd scoring && uv run python -m spike.eval --help

# backend (Milestone 2)
cd backend && uv sync && uv run pytest
cd backend && uv run alembic upgrade head     # against a Neon branch URL

# app (Milestone 3)
cd app && npm install && npm test && npx expo start
```

## Milestones

| # | Milestone | Status |
|---|---|---|
| 0 | Pronunciation scoring spike (+ local review page to listen to test recordings) | Done (spike) — see `scoring/spike/RESULTS.md`. Open: Commons recordings (rate-limited), vowel-length accuracy, advisor labels |
| 0b | Sanskrit tooling spike (sandhi/morphology) | Not started |
| 1 | Data model + migrations + seed (10 shlokas, verified flag, sources) | Not started |
| 2 | Backend API + Clerk auth (+ admin/advisor routes) | Not started |
| 3 | Mobile app: sign-in → listen → record → feedback → meaning | Not started |
| 3b | Admin/Advisor console (recordings, shlokas, review, word labels) | Not started |
| 4 | Progress tracking | Not started |

Initial 10 shlokas: Gayatri (RV 3.62.10), Mahāmṛtyuñjaya (RV 7.59.12),
Asato mā (BṛU 1.3.28), Oṃ saha nāvavatu (TaitU 2.2.2), Pūrṇamadaḥ (Īśa Up),
BG 2.47, Sarve bhavantu sukhinaḥ, Guru Brahmā, Vakratuṇḍa mahākāya,
Karāgre vasate. The last four may lack a clean open-corpus source — check
Wikisource and its license.

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

## Schema draft (implemented in Milestone 1)

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
