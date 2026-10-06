"""Audio decoding via ffmpeg, so any phone format (m4a/AAC, ogg/Opus, wav) works.

All scorers work on 16 kHz mono float32: enough bandwidth for speech, small
enough to stay fast on Lambda CPUs.
"""

import shutil
import subprocess
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16_000
MAX_SECONDS = 60.0
_DECODE_TIMEOUT_S = 30


class AudioError(ValueError):
    """The file could not be decoded or breaks our limits."""


def load_audio(path: str | Path, max_seconds: float = MAX_SECONDS) -> np.ndarray:
    """Decode any ffmpeg-readable file to 16 kHz mono float32 in [-1, 1]."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is not installed")
    path = Path(path)
    if not path.is_file():
        raise AudioError(f"not a file: {path}")
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(path),
        "-t",
        str(max_seconds + 0.5),  # decode just past the limit so we can reject
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "f32le",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=_DECODE_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired as e:
        raise AudioError("decoding timed out") from e
    if proc.returncode != 0:
        raise AudioError(f"could not decode audio: {proc.stderr.decode(errors='replace')[:200]}")
    y = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    if y.size == 0:
        raise AudioError("audio is empty")
    if y.size / SAMPLE_RATE > max_seconds:
        raise AudioError(f"audio longer than {max_seconds:.0f} s")
    return y


def save_wav(path: str | Path, y: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    import soundfile as sf

    sf.write(str(path), np.clip(y, -1.0, 1.0), sr, subtype="PCM_16")


def ffmpeg_filter(y: np.ndarray, audio_filter: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Run raw audio through an ffmpeg audio filter (e.g. rubberband) and back."""
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-f",
        "f32le",
        "-ar",
        str(sr),
        "-ac",
        "1",
        "-i",
        "-",
        "-af",
        audio_filter,
        "-f",
        "f32le",
        "-ar",
        str(sr),
        "-ac",
        "1",
        "-",
    ]
    proc = subprocess.run(
        cmd,
        input=y.astype(np.float32).tobytes(),
        capture_output=True,
        timeout=_DECODE_TIMEOUT_S,
        check=False,
    )
    if proc.returncode != 0:
        raise AudioError(f"ffmpeg filter failed: {proc.stderr.decode(errors='replace')[:200]}")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()
