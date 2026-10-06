"""Vedic Voice pronunciation scoring.

Compares a learner's chant with a verified reference recording and returns an
overall score plus per-word scores and plain-language issues.
"""

from vv_scoring.types import ScoreResult, Word, WordMark, WordScore

__all__ = ["ScoreResult", "Word", "WordMark", "WordScore"]
