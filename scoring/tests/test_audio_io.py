import subprocess

import numpy as np
import pytest

from vv_scoring.audio_io import SAMPLE_RATE, AudioError, load_audio, save_wav


def test_wav_round_trip(tmp_path):
    y = 0.5 * np.sin(2 * np.pi * 220 * np.arange(SAMPLE_RATE) / SAMPLE_RATE).astype(np.float32)
    save_wav(tmp_path / "a.wav", y)
    out = load_audio(tmp_path / "a.wav")
    assert abs(len(out) - SAMPLE_RATE) < 10
    assert np.corrcoef(out[:15000], y[:15000])[0, 1] > 0.99


def test_decodes_compressed_phone_format(tmp_path):
    """Phones upload AAC/m4a mono ~32 kbps; make sure that path decodes."""
    y = 0.5 * np.sin(2 * np.pi * 220 * np.arange(SAMPLE_RATE) / SAMPLE_RATE).astype(np.float32)
    save_wav(tmp_path / "a.wav", y)
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(tmp_path / "a.wav"),
            "-ac",
            "1",
            "-c:a",
            "aac",
            "-b:a",
            "32k",
            str(tmp_path / "a.m4a"),
        ],
        check=True,
    )
    out = load_audio(tmp_path / "a.m4a")
    assert 0.9 * SAMPLE_RATE < len(out) < 1.1 * SAMPLE_RATE


def test_rejects_too_long(tmp_path):
    save_wav(tmp_path / "long.wav", np.zeros(3 * SAMPLE_RATE, dtype=np.float32))
    with pytest.raises(AudioError, match="longer than"):
        load_audio(tmp_path / "long.wav", max_seconds=2)


def test_rejects_non_audio(tmp_path):
    (tmp_path / "x.m4a").write_bytes(b"not audio at all")
    with pytest.raises(AudioError):
        load_audio(tmp_path / "x.m4a")


def test_rejects_missing_file(tmp_path):
    with pytest.raises(AudioError, match="not a file"):
        load_audio(tmp_path / "missing.wav")
