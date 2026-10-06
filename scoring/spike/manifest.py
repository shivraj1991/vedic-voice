"""Test-set manifest: reference recording + attempts with per-word labels.

shloka: fixtures/gayatri.yaml          # relative to this manifest
reference:
  audio: ref.wav
  license: CC BY-SA 4.0                # required for public recordings
  attribution: "Name, source URL"
  marks: [[0, 0.30, 0.71], ...]        # [position, start_s, end_s]
attempts:
  - id: spk2-correct
    audio: spk2.wav
    group: speaker                     # free text, used for grouping in the report
    labels: {0: ok, 9: too_short}      # missing positions default to ok
    rating: 8                          # optional advisor 1–10 rating
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from vv_scoring.types import Word, WordMark

ISSUE_CODES = {"ok", "skipped", "too_short", "too_long", "sound_mismatch", "minor"}


@dataclass
class Attempt:
    id: str
    audio: Path
    group: str
    labels: dict[int, str]
    rating: float | None = None
    note: str = ""


@dataclass
class Manifest:
    root: Path
    words: list[Word]
    ref_audio: Path
    ref_marks: list[WordMark]
    ref_license: str
    ref_attribution: str
    attempts: list[Attempt] = field(default_factory=list)


def load(path: str | Path) -> Manifest:
    path = Path(path)
    root = path.parent
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    shloka = yaml.safe_load((root / data["shloka"]).read_text(encoding="utf-8"))
    words = [Word(i, w) for i, w in enumerate(shloka["words"])]
    ref = data["reference"]
    if not ref.get("license"):
        raise ValueError("reference.license is required (content rule: recorded licenses)")
    marks = [WordMark(int(p), float(s), float(e)) for p, s, e in ref["marks"]]
    attempts = []
    for a in data.get("attempts", []):
        labels = {w.position: "ok" for w in words} | {
            int(k): v for k, v in (a.get("labels") or {}).items()
        }
        bad = set(labels.values()) - ISSUE_CODES
        if bad:
            raise ValueError(f"attempt {a['id']}: unknown label(s) {bad}")
        attempts.append(
            Attempt(
                a["id"],
                root / a["audio"],
                a.get("group", ""),
                labels,
                a.get("rating"),
                a.get("note", ""),
            )
        )
    return Manifest(
        root,
        words,
        root / ref["audio"],
        marks,
        ref["license"],
        ref.get("attribution", ""),
        attempts,
    )


def dump(m: Manifest, shloka_rel: str, path: Path) -> None:
    def rel(p: Path) -> str:
        return str(p.relative_to(m.root))

    data = {
        "shloka": shloka_rel,
        "reference": {
            "audio": rel(m.ref_audio),
            "license": m.ref_license,
            "attribution": m.ref_attribution,
            "marks": [[k.position, round(k.start_s, 3), round(k.end_s, 3)] for k in m.ref_marks],
        },
        "attempts": [
            {
                "id": a.id,
                "audio": rel(a.audio),
                "group": a.group,
                "note": a.note,
                "labels": {p: v for p, v in a.labels.items() if v != "ok"},
            }
            for a in m.attempts
        ],
    }
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
