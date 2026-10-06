"""Approach A: Dynamic Time Warping on acoustic features.

How it works:
1. Trim silence and extract features from reference and attempt.
   Vocal-tract-length normalization (VTLN): try a few frequency warps of the
   attempt and keep the one that best matches the reference, so a child's or
   woman's voice is not penalized against a male reference (in the spike this
   removed all false alarms on synthetic voices).
2. DTW finds the best frame-to-frame alignment, absorbing tempo differences.
3. Each reference word's frames are projected onto the attempt through the
   alignment path, giving the word's span in the attempt.
4. Per word: mean alignment cost (does it *sound* the same?) and duration
   ratio relative to the learner's overall tempo (vowel length, skipped words).

Needs no Sanskrit model. It cannot say *which* sound was wrong; that is
what the phoneme (CTC) scorer adds.
"""

from collections.abc import Callable
from dataclasses import dataclass

import librosa
import numpy as np
from scipy.spatial.distance import cdist

from vv_scoring import issues
from vv_scoring.audio_io import SAMPLE_RATE
from vv_scoring.features import mfcc_features, seconds_to_frame, trim_silence
from vv_scoring.scorers.base import PASS_THRESHOLD
from vv_scoring.types import ScoreResult, Word, WordMark, WordScore


@dataclass(frozen=True)
class Calibration:
    """Maps raw measurements to 0–100. Tuned in the spike, not hard truths."""

    good_cost: float = 0.30  # mean cosine distance at/below which sound is "same"
    bad_cost: float = 0.60  # at/above which sound is "different"
    duration_tolerance: float = 1.30  # ratio within ×/÷ this is not penalized
    duration_limit: float = 2.50  # ratio beyond ×/÷ this scores 0 on duration


class DtwScorer:
    name = "dtw-mfcc"
    version = "0.2.0"

    def __init__(
        self,
        features: Callable[[np.ndarray], np.ndarray] = mfcc_features,
        calibration: Calibration = Calibration(),
        band_radius: float = 0.3,
        vtln_warps: tuple[float, ...] = (0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25),
    ) -> None:
        self.features = features
        self.cal = calibration
        self.band_radius = band_radius
        self.vtln_warps = vtln_warps or (1.0,)

    def score(
        self,
        ref_audio: np.ndarray,
        ref_marks: list[WordMark],
        attempt_audio: np.ndarray,
        words: list[Word],
    ) -> ScoreResult:
        _check_inputs(ref_marks, words)
        ref_y, ref_off = trim_silence(ref_audio)
        att_y, _ = trim_silence(attempt_audio)
        ref_f = self.features(ref_y)
        warp, att_f, cost, path = min(
            (self._try_warp(ref_f, att_y, w) for w in self.vtln_warps),
            key=lambda t: float(t[2][t[3][:, 0], t[3][:, 1]].mean()),
        )

        tempo = len(att_f) / len(ref_f)  # learner's overall speed vs reference
        scored = []
        for word, mark in zip(words, ref_marks, strict=True):
            s = max(0, seconds_to_frame(mark.start_s - ref_off))
            e = min(len(ref_f), max(s + 1, seconds_to_frame(mark.end_s - ref_off)))
            scored.append(self._score_word(word, cost, path, s, e, tempo))

        overall = round(float(np.mean([w.score for w in scored]))) if scored else 0
        return ScoreResult(overall, scored, self.name, self.version, {"vtln_warp": warp})

    def _try_warp(self, ref_f: np.ndarray, att_y: np.ndarray, warp: float):
        """Features, cost matrix and path for the attempt with formants scaled by 1/warp.

        Resampling to sr*warp and reading back at sr scales every frequency by
        1/warp (durations scale too; the tempo normalization absorbs that).
        """
        y = (
            att_y
            if warp == 1.0
            else librosa.resample(att_y, orig_sr=SAMPLE_RATE, target_sr=int(SAMPLE_RATE * warp))
        )
        att_f = self.features(y)
        cost = cdist(ref_f, att_f, metric="cosine")
        return warp, att_f, cost, self._align(cost)

    def _align(self, cost: np.ndarray) -> np.ndarray:
        _, wp = librosa.sequence.dtw(
            C=cost, global_constraints=True, band_rad=self.band_radius, backtrack=True
        )
        return wp[::-1]  # (ref_frame, attempt_frame) pairs in time order

    def _score_word(
        self, word: Word, cost: np.ndarray, path: np.ndarray, s: int, e: int, tempo: float
    ) -> WordScore:
        mask = (path[:, 0] >= s) & (path[:, 0] < e)
        pts = path[mask]
        word_cost = float(cost[pts[:, 0], pts[:, 1]].mean())
        att_len = int(pts[:, 1].max() - pts[:, 1].min() + 1)
        ratio = (att_len / (e - s)) / tempo

        q_sound = _ramp_down(word_cost, self.cal.good_cost, self.cal.bad_cost)
        q_dur = _ramp_down(
            abs(np.log(ratio)), np.log(self.cal.duration_tolerance), np.log(self.cal.duration_limit)
        )
        score = round(100 * q_sound * q_dur)
        ws = WordScore(
            word.position,
            word.iast,
            score,
            details={"cost": word_cost, "duration_ratio": ratio, "q_sound": q_sound},
        )
        if score < PASS_THRESHOLD:
            ws.issue_code, ws.issue_text = issues.describe(word.iast, ratio, q_sound)
        return ws


def _ramp_down(x: float, lo: float, hi: float) -> float:
    """1 at/below lo, 0 at/above hi, linear in between."""
    return float(np.clip((hi - x) / (hi - lo), 0.0, 1.0))


def _check_inputs(marks: list[WordMark], words: list[Word]) -> None:
    if len(marks) != len(words) or not words:
        raise ValueError("need one reference mark per word")
    if [m.position for m in marks] != [w.position for w in words]:
        raise ValueError("marks and words must be in the same order")


__all__ = ["Calibration", "DtwScorer", "SAMPLE_RATE"]
