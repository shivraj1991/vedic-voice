"""Test corpus loading for the scoring spike.

Two sources, both with recorded licenses (spike/recordings.yaml):
- Su-śrotā in-the-wild test split (CC BY 4.0): many speakers reading the same
  Sanskrit texts, so recordings of one text can be scored against each other.
- Individual Wikimedia Commons recordings (CC0 / CC BY-SA / FAL), if downloaded.
"""

from __future__ import annotations

import hashlib
import io
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from vv_scoring.audio import SAMPLE_RATE, AudioError, load_audio
from vv_scoring.phonology import PhonologyError, parse_text
from vv_scoring.translit import deva_to_iast

SPIKE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = SPIKE_DIR / "audio"
MANIFEST = SPIKE_DIR / "recordings.yaml"


@dataclass
class Recording:
    id: str
    group: str  # recordings in one group share the same text
    text: str  # IAST
    audio: np.ndarray
    license: str
    attribution: str
    source_url: str

    @property
    def sha1(self) -> str:
        return hashlib.sha1(self.audio.tobytes()).hexdigest()

    @property
    def seconds(self) -> float:
        return self.audio.size / SAMPLE_RATE


def _decode_bytes(data: bytes) -> np.ndarray:
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", "-", "-ac", "1", "-ar", str(SAMPLE_RATE),
         "-f", "f32le", "-"],
        input=data, capture_output=True, check=True,
    )  # fmt: skip
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def _usable(text: str) -> bool:
    try:
        return len(parse_text(text)) >= 2
    except PhonologyError:
        return False


def load_sushrota(manifest: dict, min_per_group: int = 2) -> list[Recording]:
    import pyarrow.parquet as pq

    ds = next(d for d in manifest["datasets"] if d["id"] == "sushrota")
    path = AUDIO_DIR / ds["local"]
    if not path.exists():
        print(f"[corpus] {path} missing; download {ds['url']}/resolve/main/{ds['file']}")
        return []
    rows = pq.read_table(path).to_pylist()
    by_text: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_text[r["text"].strip()].append((i, r))
    out = []
    for deva, items in by_text.items():
        text = deva_to_iast(deva)
        if len(items) < min_per_group or not _usable(text):
            continue
        group = "sushrota:" + hashlib.sha1(deva.encode()).hexdigest()[:8]
        for i, r in items:
            out.append(
                Recording(
                    id=f"sushrota-{i}",
                    group=group,
                    text=text,
                    audio=_decode_bytes(r["audio"]["bytes"]),
                    license=ds["license"],
                    attribution=ds["attribution"],
                    source_url=ds["url"],
                )
            )
    return out


def load_commons(manifest: dict) -> list[Recording]:
    out = []
    for rec in manifest.get("recordings", []):
        path = AUDIO_DIR / rec["file"]
        if not path.exists():
            continue
        try:
            audio = load_audio(path)
        except AudioError as e:
            print(f"[corpus] skip {path.name}: {e}")
            continue
        out.append(
            Recording(
                id=rec["id"],
                group=f"commons:{rec['shloka']}",
                text=rec["text"],
                audio=audio,
                license=rec["license"],
                attribution=rec["attribution"],
                source_url=rec["page"],
            )
        )
    return out


def load_all() -> list[Recording]:
    manifest = yaml.safe_load(MANIFEST.read_text("utf-8"))
    return load_sushrota(manifest) + load_commons(manifest)


def wav_bytes(audio: np.ndarray) -> bytes:
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()
