"""Create attempts with known errors from any recording with word marks.

Used to build a labelled test set before advisor-labelled recordings exist.
"Neutral" changes (tempo, pitch, noise) should NOT lower scores; "error"
changes (shortened, deleted, substituted word) SHOULD be flagged.

Time/pitch changes use Rubber Band (via ffmpeg) with formants preserved: a
plain phase vocoder adds smearing artefacts that scorers rightly see as errors.
"""

import numpy as np

from vv_scoring.audio_io import SAMPLE_RATE as SR
from vv_scoring.audio_io import ffmpeg_filter
from vv_scoring.types import WordMark

Labels = dict[int, str]  # position -> "ok" or an expected issue code


def _idx(t: float) -> int:
    return int(round(t * SR))


def _stretch(y: np.ndarray, rate: float) -> np.ndarray:
    """Change speed without changing pitch. rate > 1 = faster."""
    return ffmpeg_filter(y, f"rubberband=tempo={rate:.6f}")


def _all_ok(marks: list[WordMark]) -> Labels:
    return {m.position: "ok" for m in marks}


def tempo(y: np.ndarray, marks: list[WordMark], rate: float):
    """rate > 1 = faster. Every word stays correct."""
    out = _stretch(y, rate)
    scaled = [WordMark(m.position, m.start_s / rate, m.end_s / rate) for m in marks]
    return out.astype(np.float32), scaled, _all_ok(marks)


def pitch(y: np.ndarray, marks: list[WordMark], semitones: float):
    """Different voice pitch. Every word stays correct."""
    out = ffmpeg_filter(y, f"rubberband=pitch={2 ** (semitones / 12):.6f}:formant=preserved")
    return out.astype(np.float32), list(marks), _all_ok(marks)


def noise(y: np.ndarray, marks: list[WordMark], snr_db: float, seed: int = 0):
    """Background noise at a given signal-to-noise ratio. Every word stays correct."""
    rng = np.random.default_rng(seed)
    p_sig = float(np.mean(y**2))
    n = rng.standard_normal(len(y)) * np.sqrt(p_sig / (10 ** (snr_db / 10)))
    return (y + n).astype(np.float32), list(marks), _all_ok(marks)


def _replace_segment(y, marks, pos, new_seg):
    m = next(mk for mk in marks if mk.position == pos)
    a, b = _idx(m.start_s), _idx(m.end_s)
    out = np.concatenate([y[:a], new_seg, y[b:]]).astype(np.float32)
    shift = len(new_seg) / SR - (m.end_s - m.start_s)
    new_marks = []
    for mk in marks:
        if mk.position < pos:
            new_marks.append(mk)
        elif mk.position == pos:
            new_marks.append(WordMark(pos, m.start_s, max(m.start_s + 0.01, m.end_s + shift)))
        else:
            new_marks.append(WordMark(mk.position, mk.start_s + shift, mk.end_s + shift))
    return out, new_marks


def shorten_word(y: np.ndarray, marks: list[WordMark], pos: int, factor: float = 0.5):
    """Squash one word to `factor` of its length (simulates rushed long vowels)."""
    m = next(mk for mk in marks if mk.position == pos)
    seg = y[_idx(m.start_s) : _idx(m.end_s)]
    out, new_marks = _replace_segment(y, marks, pos, _stretch(seg, 1 / factor))
    labels = _all_ok(marks) | {pos: "too_short"}
    return out, new_marks, labels


def delete_word(y: np.ndarray, marks: list[WordMark], pos: int):
    out, new_marks = _replace_segment(y, marks, pos, np.zeros(int(0.01 * SR), dtype=np.float32))
    return out, new_marks, _all_ok(marks) | {pos: "skipped"}


def substitute_word(y: np.ndarray, marks: list[WordMark], pos: int, with_pos: int):
    """Put another word's audio where `pos` should be (a clearly wrong word)."""
    src = next(mk for mk in marks if mk.position == with_pos)
    seg = y[_idx(src.start_s) : _idx(src.end_s)].copy()
    out, new_marks = _replace_segment(y, marks, pos, seg)
    return out, new_marks, _all_ok(marks) | {pos: "sound_mismatch"}
