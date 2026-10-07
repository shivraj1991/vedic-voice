#!/bin/bash
# Prepare a Claude Code cloud session: Python deps for scoring/, plus the
# 4-bit phoneme model and the Su-śrotā test split so `spike.eval` runs.
# Idempotent: uv sync is a no-op when locked deps are installed, and
# spike.fetch skips files whose sha256 already matches.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR/scoring"
uv sync --quiet

# ~290 MB from huggingface.co. Needs that host in the environment's network
# allowlist; don't fail the session if it is blocked (unit tests don't need it).
if ! uv run --quiet python -m spike.fetch --skip-fp32; then
  echo "session-start: model/test-data download failed (is huggingface.co allowed?)" >&2
fi
