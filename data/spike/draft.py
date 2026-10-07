"""Draft word analyses for shlokas, for advisor review (never shown to learners).

    uv run python -m spike.draft            # writes spike/out/drafts/*.yaml

Each draft lists, per pada, where the split came from and every lexicon reading;
`verified: false` until an advisor confirms it in the console (Milestone 3b).
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

import yaml

from vv_content.analysis import TOOL, TOOL_VERSION, Toolkit

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"

# (slug, source id in data/sources.yaml, reference, how to get the text)
SHLOKAS = [
    ("gayatri", "gretil-rigveda-aufrecht", "RV 3.62.10", ("rv", "rv_3,62.10")),
    ("mahamrityunjaya", "gretil-rigveda-aufrecht", "RV 7.59.12", ("rv", "rv_7,59.12")),
    ("bg-2-47", "gretil-bhagavadgita", "BhG 2.47", ("bhg", "02.047")),
]


def _rv(ref: str) -> tuple[str, str]:
    """Saṃhitā text and pada-pāṭha line for a Ṛgveda verse (GRETIL)."""
    pp = (VENDOR / "rv_padapatha.txt").read_text("utf-8").splitlines()
    pada_line = next(line for line in pp if f"// {ref} //" in line)
    m, s, v = re.match(r"rv_(\d+),(\d+)\.(\d+)", ref).groups()
    key = f"RV_{int(m)},{int(s):03d}.{int(v):02d}"
    lines = (VENDOR / "rv_samhita.txt").read_text("utf-8").splitlines()
    end = next(i for i, line in enumerate(lines) if key in line)
    start = end
    while start > 0 and lines[start - 1].strip():
        start -= 1
    text = " ".join(lines[start : end + 1])
    text = re.sub(r"RV_\S+|[|/]", " ", text)
    return " ".join(text.split()), pada_line


def _bhg(ref: str) -> str:
    raw = (VENDOR / "bhagavadgita.htm").read_text("utf-8", errors="replace")
    raw = html.unescape(re.sub(r"<[^>]+>", "", raw))
    out = []
    for line in raw.splitlines():
        if re.search(rf"Bhg_{re.escape(ref)}[ac]\b", line):
            out.append(line.split("Bhg_")[0].strip())
    return " ".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "spike" / "out" / "drafts"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tk = Toolkit(VENDOR / "vidyut-0.4.0")

    for slug, source, ref, (kind, key) in SHLOKAS:
        if kind == "rv":
            text, padapatha = _rv(key)
            drafts = tk.draft_line(text, padapatha=padapatha)
        else:
            text = _bhg(key)
            drafts = tk.draft_line(text)
        doc = {
            "slug": slug,
            "iast": text,
            "source_id": source,
            "source_ref": ref,
            "verified": False,
            "analysis_tool": TOOL,
            "analysis_tool_version": TOOL_VERSION,
            "padas": [d.to_dict() for d in drafts],
        }
        path = out / f"{slug}.yaml"
        path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), "utf-8")
        statuses = [d.status for d in drafts]
        print(
            f"{slug:16} {len(drafts):2} padas  unique {statuses.count('unique')}  "
            f"ambiguous {statuses.count('ambiguous')}  unknown {statuses.count('unknown')}"
            f"  -> {path}"
        )


if __name__ == "__main__":
    main()
