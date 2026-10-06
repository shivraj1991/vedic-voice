"""Common interface so the spike can compare scorers on identical inputs."""

from typing import Protocol

import numpy as np

from vv_scoring.types import ScoreResult, Word, WordMark

PASS_THRESHOLD = 75  # word scores below this are flagged "needs work"


class Scorer(Protocol):
    name: str
    version: str

    def score(
        self,
        ref_audio: np.ndarray,
        ref_marks: list[WordMark],
        attempt_audio: np.ndarray,
        words: list[Word],
    ) -> ScoreResult: ...
