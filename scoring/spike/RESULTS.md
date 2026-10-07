# Milestone 0 — scoring spike results (2026-10-06)

Reproduce: `uv run python -m spike.fetch && uv run python -m spike.eval`
(seed 7, 40 texts, ≤6 recordings per text). Full per-case output is in
`spike/out/report.json`, and you can listen in `spike/out/review.html` (both gitignored).

## Data

- 164 recordings of 40 Sanskrit texts from the **Su-śrotā in-the-wild test split**
  (IISc, CC BY 4.0): consented phone recordings by different people reading
  the same text (stotras, Gītā, Ṛgveda 1.1.1, Bhāgavata). For each text, the
  recording that best fits the text is used as the "reference". The others are the "learners".
- Wikimedia Commons recordings (Gayatri ×2, Mahāmṛtyuñjaya, BG 3.1; CC0/FAL/CC BY-SA)
  are in `recordings.yaml`, but upload.wikimedia.org answered 429 to the dev
  sandbox all day, so they are **not in these numbers**. Run
  `spike.fetch --commons` from a normal network.

No advisor labels exist yet, so the ground truth comes from **controlled edits** of
real recordings (we know which word we broke):

| case | what we did | what should happen |
|---|---|---|
| clean | unedited learner vs reference | high score, few flags (unlabelled: some flags may be real mistakes) |
| deletion | cut one word out | that word flagged |
| substitute | replaced one word with a similar-length word from another text | that word flagged |
| vowel_short | shortened one long vowel to 40% | that word flagged |
| noise | white noise at 10 dB SNR | few extra flags |
| wrong_text | audio scored against another text | low match confidence |

## Results (fp32 model, tuned calibration)

| case kind | n | overall | match | target recall | target is lowest word | false-flag rate (other words) |
|---|---|---|---|---|---|---|
| clean | 124 | 86.2 | 0.941 | – | – | **0.103** |
| noise | 124 | 79.5 | 0.901 | – | – | 0.193 |
| deletion | 124 | 67.5 | 0.665 | **1.000** | 0.839 | 0.289 |
| substitute | 124 | 76.5 | 0.818 | **0.879** | 0.758 | 0.144 |
| vowel_short | 121 | 81.2 | 0.938 | **0.612** | 0.678 | 0.089 |
| wrong_text | 124 | 59.6 | 0.551 | – | – | – |

- **Wrong-text detection works:** clean vs wrong-text match confidence AUC = 0.999.
  At a threshold of 0.878, 100% of wrong-text cases are rejected and 95% of clean ones are kept.
- **Gross errors (missing or wrong word) are caught reliably.** Neighbouring words
  are sometimes flagged too (deletion false-flag rate 0.29): in two-word texts the
  alignment smears the gap into the neighbour.
- **Vowel length is the weakest signal (61% recall).** The CTC model is spiky, so
  durations are only a rough measure. This matters for chanting and is the first thing to improve.
- **False flags on clean audio: 10% of words**, down from 40% before calibration.
  Most of the remaining flags are single-consonant issues (ś→s, aspiration) and
  short words. Some may be genuine; this needs advisor labels to split.
- Analysis after the model runs: ~0.15 s per recording. Model: ~0.2 s per audio second
  on 4 vCPU (fp32), so ~12 s for a 60 s chant before any Lambda tuning.

### Calibration history

| change | clean false-flag | recall |
|---|---|---|
| first version (any unit deletion flagged) | 0.40 | 0.89 |
| single-sound deletions down-weighted and need a bigger deficit | 0.24 | 0.88 |
| "word missing" only when clearly worse than the reference | 0.10 | 0.83 |

## Quantised model (model_q4.onnx, 230 MB vs 1.2 GB)

Same cases, same calibration (`--onnx-file model_q4.onnx`):

| case kind | target recall (fp32 → q4) | false-flag rate (fp32 → q4) |
|---|---|---|
| clean | – | 0.103 → 0.092 |
| deletion | 1.000 → 0.992 | 0.289 → 0.269 |
| substitute | 0.879 → 0.855 | 0.144 → 0.125 |
| vowel_short | 0.612 → 0.579 | 0.089 → 0.086 |

Wrong-text AUC is 0.999 for both. Speed is the same on CPU (0.18 s per audio second).
**q4 is about as accurate at a fifth of the size** (230 MB vs 1.2 GB), which keeps the
scoring container image near the ECR 500 MB free tier. Recommendation: ship q4,
and keep fp32 for offline evaluation.

## What the spike tells us

1. **Approach is viable for the MVP's main promise** of flagging the words that need
   work: missing or wrong words, sibilants, aspiration. Every flag has a
   plain-language reason from a curated table, not model output.
2. **Calibrate against the reference.** Without it, the model's blind spots
   (retroflexes, short vowels) become false flags.
3. **Vowel length needs more work:** a frame-level vowel detector or an
   energy/voicing-based duration measure instead of CTC spike spacing.
4. **Next ground truth:** advisor labels via the review page's export
   (`word_labels` shape), then re-tune on real mistakes instead of synthetic edits.
5. **Production model:** re-export ONNX ourselves from the Facebook checkpoint, then
   quantise to 4-bit (accuracy is about the same, see above).
