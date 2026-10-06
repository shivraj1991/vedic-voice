# Milestone 0 report: pronunciation scoring (INTERIM)

Status: **interim**. Approach A (DTW) is built and measured on a synthetic
set. Approaches B (phoneme CTC + forced alignment + GOP) and C (Whisper
baseline) need model downloads from Hugging Face / OpenAI, which this
environment's network policy blocked; real public recordings (Wikimedia) were
blocked too. Nothing below has been measured on a human voice yet.

## Pass bar (agreed in planning)

| Metric | Target |
|---|---|
| Word-level error detection F1 vs advisor labels | ≥ 0.75 |
| False alarms on correct words | ≤ 10% |
| Spearman(overall score, advisor 1–10 rating) | ≥ 0.6 |
| Voice/tempo/pitch robustness (score drop on correct chants) | < 5 points |
| Latency, 30 s clip, CPU | < 5 s |

## Test set (synthetic)

Gayatri (14 words). Reference = synthetic male voice. 24 attempts:
4 correct voices (female slow, male fast, child, male), 6 neutral changes
(tempo 0.8/1.25, pitch ±3 semitones, noise 20/10 dB), 3 skipped words,
3 rushed words (word squashed to 50%), 3 wrong words, 5 sound errors
(ī→i, ā→a, bh→b, ṇ→n, s→sh). 336 labelled words.

The synthesizer is crude (formant vowels, noise-burst consonants). It is good
for checking behaviour with exact ground truth, not for absolute accuracy.

## Results: Approach A — DTW on acoustic features

| Version | F1 | Precision | Recall | False alarms | Neutral mean / min | Latency |
|---|---|---|---|---|---|---|
| MFCC 1–13 (40 mel), probe only | – | – | – | pitch ±3 scored 14–58 overall | – | 0.1 s |
| MFCC 1–8 (20 mel) | 0.42 | 0.37 | 0.50 | 3.7% | 95.5 / 65 | 0.11 s |
| + VTLN (chosen) | **0.61** | 0.78 | 0.50 | **0.6%** | **100 / 100** | 0.46 s |

Recall by error type (with VTLN): skipped 0.67, rushed (too_short) 0.60
(rushed words 3/3; the vowel-only errors ī→i and ā→a 0/2), wrong word /
sound errors 0.33 (gross wrong words 2/3; subtle phone errors 0/3).

### What we learned

1. **Catches:** wrong words, rushed words, most skipped words. Issue code
   was right for every correctly flagged word.
2. **Misses all subtle sound errors** (vowel length inside a word,
   aspiration, retroflex vs dental). These are the errors learners make most,
   so DTW alone cannot meet the bar.
3. **Localisation slips on similar neighbours:** skipping *bhuvaḥ* blamed
   *svaḥ* and *tat* instead.
4. **Voice robustness needed work:** high voices produced many false alarms
   until VTLN (search over frequency warps 0.85–1.25). VTLN removed all false
   alarms here, but the synthetic voices differ exactly the way VTLN corrects,
   so expect less benefit on real voices.
5. **Tooling lesson:** phase-vocoder time/pitch shifting (librosa) adds
   artefacts that look like errors; perturbations now use Rubber Band.

## Approaches B and C

Not yet run (blocked downloads). Plan:
- **B:** `facebook/wav2vec2-xlsr-53-espeak-cv-ft` (phoneme CTC) and an
  AI4Bharat Indic CTC model; force-align the expected phones from
  `phonemes.tokenize` to the attempt (`torchaudio.functional.forced_align`);
  GOP per phone → per word; aligned vowel durations for length errors. Also
  produces reference word marks automatically.
- **C:** `faster-whisper` with `language=sa` and `hi`; character edit distance
  per word. Baseline only.
- **Hybrid:** B for which sound, A's tempo-normalised durations for length.

## Interim recommendation

Keep DTW+VTLN as the duration/skip/wrong-word layer; it is cheap (no model,
<0.5 s). Do not ship it alone: it cannot hear the sound errors that matter.
Decide after B is measured on real recordings.
