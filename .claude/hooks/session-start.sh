#!/bin/bash
# Prepare a Claude Code cloud session so tests, linters and spikes run:
# - scoring/: Python deps, 4-bit phoneme model, Su-śrotā test split
# - data/:    Python deps, Vidyut data bundle, GRETIL/Wikisource texts
# - backend/: Python deps (tests start a local PostgreSQL if binaries exist)
# Idempotent: uv sync is a no-op when locked deps are installed; the fetch
# scripts skip files that are already present / match their sha256.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR/scoring"
uv sync --quiet
# Downloads need huggingface.co (and github.com / gretil for data/) in the
# environment's network allowlist. Don't fail the session if they are blocked:
# unit tests don't need them.
if ! uv run --quiet python -m spike.fetch --skip-fp32; then
  echo "session-start: scoring model/test-data download failed (is huggingface.co allowed?)" >&2
fi

cd "$CLAUDE_PROJECT_DIR/data"
uv sync --quiet
if ! uv run --quiet python -m spike.fetch; then
  echo "session-start: data download failed (github.com releases / gretil allowed?)" >&2
fi

cd "$CLAUDE_PROJECT_DIR/backend"
uv sync --quiet
