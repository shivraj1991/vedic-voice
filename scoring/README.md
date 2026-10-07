# vv_scoring — pronunciation scoring

Scores a learner's chant of a shloka against the scholar reference recording:
an overall score, a 0–100 score per word, and a plain-language issue for weak
words ("In "vareṇyaṃ": curl the tongue tip back for "ṇ"; it sounded like dental "n"").

## How it works

```
audio (m4a/ogg/wav) ──ffmpeg──► 16 kHz mono
        │
        ▼
wav2vec2 XLSR-53 espeak (ONNX, onnxruntime)  →  frame log-posteriors over 392 IPA tokens
        │
        ▼
IAST text ──rule-based phonology──► Sanskrit units (a ā … kh … ś ṣ ṃ ḥ, jñ, geminates)
        │                            each with accepted token realisations + curated confusions
        ▼
CTC alignment over a small graph (alternative realisations, start/end filler for extra speech)
        │
        ▼
GOP per unit = log P(expected) − max log P(curated alternative)   (local window, CTC forward)
        │
        ▼
score vs reference: deficit = min(GOP_ref, cap) − GOP_learner → unit/word scores,
issue = the alternative that won (+ long-vowel duration check vs reference)
```

Design choices:

- **Phones, not words.** A phoneme model does not "autocorrect" a mispronunciation
  into a dictionary word, and it is language-agnostic (no Sanskrit ASR needed).
- **Curated confusions only.** We only test for mistakes we can explain
  (`phonology.CONFUSIONS`: long/short vowels, aspiration, retroflex vs dental,
  ś/ṣ vs s, dropped sounds). Each has an `issue_code` and a plain-language template.
- **Reference-calibrated.** The model is weak on some Sanskrit sounds (it rarely
  outputs retroflex tokens). The same GOP is computed for the reference
  recording, and the learner is only blamed where they do clearly worse than
  the scholar on that sound. Reference analyses are cacheable
  (`RecordingAnalysis.to_dict()`), so production computes them once per
  reference audio, not per attempt.
- **Grammar stays deterministic.** IAST tokenisation, transliteration and the
  confusion tables are rule-based code; no LLM is involved in scoring.
- **Swara (pitch accent) is not scored** (MVP decision); accent marks are stripped.

## Use

```python
from vv_scoring.audio import load_audio
from vv_scoring.model import PhonemeModel
from vv_scoring.scorer import analyse, score

model = PhonemeModel("models/w2v2-xlsr53-espeak")  # load once per process
text = "tat savitur vareṇyaṃ bhargo devasya dhīmahi dhiyo yo naḥ pracodayāt"
ref = analyse(model.posteriors(load_audio("reference.m4a")), text)  # cache this
result = score(analyse(model.posteriors(load_audio("attempt.m4a")), text), ref)
result.to_dict()  # overall, match_confidence, words[{text, score, start_ms, end_ms, issue_code, issue_text}]
```

`match_confidence` near 1 means the audio fits the text; low values mean the
learner chanted something else (or nothing). Callers should treat a low match
as "we couldn't match your chant to this shloka" rather than showing word scores.

## Commands

```
uv sync
uv run pytest                      # unit tests (synthetic posteriors; no model needed)
uv run ruff check . && uv run ruff format --check .
uv run python -m spike.fetch       # model (pinned, sha256) + Su-śrotā test split
uv run python -m spike.fetch --commons   # + Wikimedia Commons recordings (rate-limited)
uv run python -m spike.eval --help
uv run python -m spike.eval        # writes spike/out/{summary.md,report.json,review.html}
```

Open `spike/out/review.html` in a browser to listen to every case and label words.

## Spike results

See [`spike/RESULTS.md`](spike/RESULTS.md).
