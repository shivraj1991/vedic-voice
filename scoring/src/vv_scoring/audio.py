"""Audio decoding.

We shell out to ffmpeg instead of adding a Python codec dependency: ffmpeg is
already required in the scoring Lambda image, it reads every format the app or
the test corpus produces (m4a/AAC, ogg/vorbis, wav, opus), and it resamples to
the 16 kHz mono float32 the acoustic model expects.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16_000
MAX_SECONDS = 120.0  # hard ceiling; product limit is 60 s, reference audio may be longer


class AudioError(ValueError):
    """Raised when audio cannot be decoded or is outside accepted limits."""


def load_audio(path: str | Path, max_seconds: float = MAX_SECONDS) -> np.ndarray:
    """Decode any ffmpeg-readable file to mono float32 at 16 kHz."""
    if shutil.which("ffmpeg") is None:
        raise AudioError("ffmpeg not found on PATH")
    cmd = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
        "-t", str(max_seconds), "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-",
    ]  # fmt: skip
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0:
        raise AudioError(f"ffmpeg failed: {proc.stderr.decode(errors='replace').strip()[:300]}")
    audio = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    if audio.size < SAMPLE_RATE // 2:
        raise AudioError("audio shorter than 0.5 s")
    return audio


def save_wav(path: str | Path, audio: np.ndarray) -> None:
    """Write 16 kHz mono PCM16 wav (used by the spike to create perturbed test files)."""
    import wave

    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
