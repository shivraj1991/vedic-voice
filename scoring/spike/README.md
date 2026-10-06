# Milestone 0 — pronunciation scoring spike

Compare a chant with a reference at word level; measure accuracy against labels.

```
cd scoring
uv sync
uv run pytest                                   # unit + end-to-end tests
uv run python -m spike.eval --synthetic         # build synthetic set, score, report
uv run python -m spike.eval --manifest path/to/manifest.yaml   # real recordings
```

Outputs go to `spike/out/` (gitignored): `results.json` and `review.html`.
Open `review.html` in a browser to listen to each recording next to its
per-word scores. A red outline marks words labelled as errors.

## Adding real recordings

1. Put the files in `spike/audio/<set>/` (gitignored; any format ffmpeg reads).
2. Write `manifest.yaml` next to them; see the docstring in `spike/manifest.py`.
   - `reference.license` and `attribution` are **required** (content rule).
   - `reference.marks` holds word start/end times in seconds. Mark them by
     hand for now (e.g. in Audacity: Label Track → export labels). The CTC
     scorer will be able to produce these automatically.
   - `labels` per attempt: `ok`, `too_short`, `too_long`, `skipped`,
     `sound_mismatch`. `rating` is an optional advisor 1–10 score.
3. Run `uv run python -m spike.eval --manifest spike/audio/<set>/manifest.yaml --out spike/out/<set>`.

## Layout

| Path | What |
|---|---|
| `vv_scoring/scorers/dtw.py` | Approach A: VTLN + DTW on low-order MFCC |
| `vv_scoring/phonemes.py` | Rule-based IAST → phones (length, aspiration, retroflex) |
| `vv_scoring/issues.py` | Measurements → plain-language issue |
| `vv_scoring/perturb.py` | Known-error attempts from any marked recording |
| `vv_scoring/synth.py` | Formant synthesizer, tests/synthetic set only |
| `spike/eval.py`, `metrics.py`, `review.py` | Harness, metrics, listening page |
| `spike/REPORT.md` | Results and recommendation |
