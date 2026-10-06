"""Acoustic features for alignment.

Low-order MFCCs (1–8, from 20 mel bands) without c0 (loudness) plus deltas,
with per-utterance mean/variance normalization. Few, wide bands describe the
vocal-tract shape (what was said) rather than harmonics (voice pitch): in the
spike this halved the penalty for a ±3 semitone voice change while still
separating wrong words. Trade-off: subtle sound differences blur too.
This is the baseline extractor; self-supervised features (wav2vec2/WavLM)
plug in through the same `(frames, dims)` interface.
"""

import librosa
import numpy as np

from vv_scoring.audio_io import SAMPLE_RATE

HOP_S = 0.010  # 10 ms frames
_N_FFT = 400  # 25 ms window


def frame_to_seconds(frame: int | np.ndarray) -> float | np.ndarray:
    return frame * HOP_S


def seconds_to_frame(t: float) -> int:
    return int(round(t / HOP_S))


def mfcc_features(y: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Return a (frames, 16) matrix: MFCC 1–8 and their deltas, CMVN-normalized."""
    hop = int(sr * HOP_S)
    m = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=9, n_fft=_N_FFT, hop_length=hop, n_mels=20)
    m = m[1:]  # drop c0: overall loudness is not pronunciation
    d = librosa.feature.delta(m, width=5) if m.shape[1] >= 5 else np.zeros_like(m)
    feats = np.vstack([m, d]).T
    mu = feats.mean(axis=0, keepdims=True)
    sd = feats.std(axis=0, keepdims=True) + 1e-6
    return ((feats - mu) / sd).astype(np.float32)


def trim_silence(y: np.ndarray, top_db: float = 35.0) -> tuple[np.ndarray, float]:
    """Trim leading/trailing silence. Returns (trimmed audio, offset in seconds)."""
    trimmed, idx = librosa.effects.trim(y, top_db=top_db, frame_length=_N_FFT, hop_length=160)
    if trimmed.size == 0:
        return y, 0.0
    return trimmed, idx[0] / SAMPLE_RATE
