"""Turn per-word measurements into a short, plain-language issue.

Rules are deliberately simple and explainable. The CTC scorer will add
sound-specific messages (aspiration, retroflex) once it can name phones.
"""

from vv_scoring.phonemes import long_vowels

# Normalized duration ratio = (word length in attempt / in reference),
# after removing the learner's overall tempo.
SKIPPED_RATIO = 0.30
SHORT_RATIO = 0.70
LONG_RATIO = 1.60


def describe(iast: str, duration_ratio: float, sound_quality: float) -> tuple[str, str]:
    """Return (issue_code, issue_text) for a word that scored below threshold.

    `sound_quality` is 0–1 (1 = sounds like the reference).
    """
    if duration_ratio < SKIPPED_RATIO:
        return "skipped", f"'{iast}' seems to be missing or very rushed."
    if duration_ratio < SHORT_RATIO:
        vowels = long_vowels(iast)
        if vowels:
            return "too_short", f"Hold the long vowel '{vowels[0]}' in '{iast}' a little longer."
        return "too_short", f"'{iast}' was said faster than the reference."
    if duration_ratio > LONG_RATIO:
        return "too_long", f"'{iast}' was held longer than the reference."
    if sound_quality < 0.6:
        return (
            "sound_mismatch",
            f"'{iast}' sounds different from the reference. Listen and try again.",
        )
    return "minor", f"'{iast}' is close. Listen once more to match the reference."
