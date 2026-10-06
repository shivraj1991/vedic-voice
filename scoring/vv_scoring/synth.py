"""Tiny formant synthesizer for TESTS and the synthetic spike benchmark only.

It produces vowel/consonant-like sounds with controllable speakers and exact
word timings, so we can check scorer behaviour with known ground truth
(e.g. "this long vowel was shortened"). It does not sound like real Sanskrit
and is never used as reference content.
"""

from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter

from vv_scoring.audio_io import SAMPLE_RATE
from vv_scoring.phonemes import Phone, tokenize
from vv_scoring.types import Word, WordMark

SR = SAMPLE_RATE

# (F1, F2) in Hz for an adult male voice.
_VOWEL_FORMANTS = {
    "a": (700, 1220),
    "ā": (750, 1180),
    "i": (300, 2250),
    "ī": (270, 2400),
    "u": (330, 850),
    "ū": (300, 750),
    "e": (450, 2000),
    "o": (460, 850),
    "ai": (550, 1750),
    "au": (560, 1000),
    "ṛ": (420, 1350),
    "ṝ": (420, 1350),
    "ḷ": (400, 1150),
    "ḹ": (400, 1150),
}
_SONORANTS = {  # voiced consonants rendered with formants
    "m": (250, 1000),
    "n": (250, 1500),
    "ṇ": (260, 1300),
    "ñ": (250, 2000),
    "ṅ": (250, 1700),
    "ṃ": (250, 1100),
    "y": (280, 2200),
    "r": (420, 1300),
    "l": (380, 1100),
    "v": (350, 900),
}
# Noise centre frequency for bursts/fricatives (Hz); place of articulation.
_NOISE_CENTRE = {
    "k": 1500,
    "g": 1500,
    "c": 3000,
    "j": 3000,
    "ṭ": 2200,
    "ḍ": 2200,
    "t": 3800,
    "d": 3800,
    "p": 800,
    "b": 800,
    "s": 6000,
    "ś": 3500,
    "ṣ": 2600,
    "h": 1500,
    "ḥ": 1500,
}
_VOICED_STOPS = {"g", "j", "ḍ", "d", "b"}


@dataclass(frozen=True)
class Speaker:
    f0: float = 120.0  # pitch in Hz
    formant_scale: float = 1.0  # ~1.15–1.2 for a typical female/child voice
    tempo: float = 1.0  # >1 = slower (durations multiplied)
    seed: int = 0


def _resonator(x: np.ndarray, freq: float, bw: float) -> np.ndarray:
    r = np.exp(-np.pi * bw / SR)
    theta = 2 * np.pi * freq / SR
    return lfilter([1 - r], [1, -2 * r * np.cos(theta), r * r], x)


def _voiced(dur: float, f1: float, f2: float, spk: Speaker, rng: np.random.Generator) -> np.ndarray:
    n = max(1, int(dur * SR))
    period = SR / spk.f0
    src = np.zeros(n)
    pos = 0.0
    while pos < n:
        src[int(pos)] = 1.0
        pos += period * (1 + 0.01 * rng.standard_normal())
    k = spk.formant_scale
    y = _resonator(src, f1 * k, 80) + 0.6 * _resonator(src, f2 * k, 120)
    y += 0.3 * _resonator(src, 2600 * k, 200)
    return y / (np.max(np.abs(y)) + 1e-9)


def _noise(dur: float, centre: float, spk: Speaker, rng: np.random.Generator) -> np.ndarray:
    n = max(1, int(dur * SR))
    y = _resonator(rng.standard_normal(n), min(centre * spk.formant_scale, SR / 2 - 500), 600)
    return 0.4 * y / (np.max(np.abs(y)) + 1e-9)


def _render_phone(p: Phone, prev_vowel: str, spk: Speaker, rng: np.random.Generator) -> np.ndarray:
    t = spk.tempo
    if p.kind == "vowel":
        f1, f2 = _VOWEL_FORMANTS[p.label]
        return _voiced((0.22 if p.long else 0.11) * t, f1, f2, spk, rng)
    if p.label in _SONORANTS or p.kind == "anusvara":
        f1, f2 = _SONORANTS.get(p.label, _SONORANTS["ṃ"])
        return 0.6 * _voiced(0.07 * t, f1, f2, spk, rng)
    if p.kind == "visarga":  # breath + faint echo of the previous vowel
        f1, f2 = _VOWEL_FORMANTS.get(prev_vowel, _VOWEL_FORMANTS["a"])
        return np.concatenate(
            [_noise(0.06 * t, 1500, spk, rng), 0.3 * _voiced(0.05 * t, f1, f2, spk, rng)]
        )
    base = p.label[0] if p.aspirated else p.label
    if base in ("s", "ś", "ṣ", "h"):
        return _noise(0.09 * t, _NOISE_CENTRE[base], spk, rng)
    closure = np.zeros(int(0.04 * t * SR))
    if base in _VOICED_STOPS:
        closure = 0.15 * _voiced(0.04 * t, 250, 900, spk, rng)
    parts = [closure, _noise(0.02 * t, _NOISE_CENTRE[base], spk, rng)]
    if p.aspirated:
        parts.append(_noise(0.06 * t, 1200, spk, rng))
    return np.concatenate(parts)


def _fade(x: np.ndarray, ms: float = 5) -> np.ndarray:
    n = min(len(x) // 2, int(SR * ms / 1000))
    if n > 0:
        ramp = np.linspace(0, 1, n)
        x = x.copy()
        x[:n] *= ramp
        x[-n:] *= ramp[::-1]
    return x


def synthesize(
    words: list[Word], speaker: Speaker = Speaker(), gap_s: float = 0.06, lead_s: float = 0.3
) -> tuple[np.ndarray, list[WordMark]]:
    """Render words to audio. Returns (audio, exact word marks)."""
    rng = np.random.default_rng(speaker.seed)
    chunks = [np.zeros(int(lead_s * SR))]
    marks, t = [], lead_s
    for w in words:
        prev_vowel, segs = "a", []
        for p in tokenize(w.iast):
            segs.append(_fade(_render_phone(p, prev_vowel, speaker, rng)))
            if p.kind == "vowel":
                prev_vowel = p.label
        audio = np.concatenate(segs)
        marks.append(WordMark(w.position, t, t + len(audio) / SR))
        chunks += [audio, np.zeros(int(gap_s * speaker.tempo * SR))]
        t += len(audio) / SR + gap_s * speaker.tempo
    chunks.append(np.zeros(int(lead_s * SR)))
    y = np.concatenate(chunks)
    y += 0.002 * rng.standard_normal(len(y))  # faint room noise
    return (0.8 * y / np.max(np.abs(y))).astype(np.float32), marks
