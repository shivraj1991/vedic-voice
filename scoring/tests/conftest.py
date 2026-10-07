"""Shared fixtures: a tiny fake vocabulary and synthetic posteriors.

Tests never load the real 1.2 GB model; they build frame posteriors that
"say" a given token sequence, which is enough to test alignment and scoring
logic deterministically.
"""

from __future__ import annotations

import numpy as np
import pytest

from vv_scoring.model import Posteriors

TOKENS = ["<pad>", "<s>", "</s>", "<unk>", "ə", "a", "aː", "i", "iː", "u", "uː", "e", "o",
          "t", "t̪", "ʈ", "d", "dʰ", "h", "s", "ʃ", "ʂ", "n", "ɳ", "m", "v", "ʋ", "ɾ", "j",
          "ɡ", "k", "b", "bʰ", "p", "dʒ", "ɲ", "l"]  # fmt: skip
VOCAB = {t: i for i, t in enumerate(TOKENS)}


def synth(
    tokens: list[str | tuple[str, int]],
    frames_per_token: int = 4,
    blank_frames: int = 2,
    peak: float = 0.9,
    lead: int = 5,
    tail: int = 5,
) -> Posteriors:
    """Posteriors for an utterance that clearly says `tokens` (blank-separated).

    A token may be (token, n_frames) to control its duration.
    """
    seq: list[int | None] = [None] * lead
    for t in tokens:
        tok, n = t if isinstance(t, tuple) else (t, frames_per_token)
        seq += [VOCAB[tok]] * n + [None] * blank_frames
    seq += [None] * tail
    v = len(VOCAB)
    lp = np.full((len(seq), v), (1 - peak) / (v - 1))
    for f, tok in enumerate(seq):
        idx = VOCAB["<pad>"] if tok is None else tok
        lp[f, idx] = peak
    lp /= lp.sum(axis=1, keepdims=True)
    return Posteriors(np.log(lp), VOCAB)


@pytest.fixture
def vocab() -> dict[str, int]:
    return VOCAB
