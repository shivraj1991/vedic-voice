"""Score one recording against a reference, from the command line.

    uv run python -m spike.score_file --text "tat savitur vareṇyaṃ ..." \\
        --reference scholar.m4a attempt.m4a

`--text` takes IAST or Devanagari. Prints per-word scores and issues; add
--json for the raw result.
"""

from __future__ import annotations

import argparse
import json

from vv_scoring.audio import load_audio
from vv_scoring.model import PhonemeModel
from vv_scoring.scorer import analyse, score
from vv_scoring.translit import deva_to_iast


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("attempt", help="learner recording (any ffmpeg-readable format)")
    ap.add_argument("--reference", help="reference recording of the same text (recommended)")
    ap.add_argument("--text", required=True, help="the shloka, IAST or Devanagari")
    ap.add_argument("--model-dir", default="models/w2v2-xlsr53-espeak")
    ap.add_argument("--onnx-file", default="model_q4.onnx")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = deva_to_iast(args.text)
    model = PhonemeModel(args.model_dir, args.onnx_file)
    ref = analyse(model.posteriors(load_audio(args.reference)), text) if args.reference else None
    result = score(analyse(model.posteriors(load_audio(args.attempt)), text), ref)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=1))
        return
    print(f"overall {result.overall}   match confidence {result.match_confidence}")
    if result.match_confidence < 0.88:
        print("  (low match: the recording may not be this text)")
    for w in result.words:
        line = f"  {w.text:<20} {w.score:>3}  {w.start_ms / 1000:5.2f}-{w.end_ms / 1000:5.2f}s"
        print(line + (f"  {w.issue_text}" if w.issue_text else ""))
    if ref is None:
        print("note: no --reference given; scores are uncalibrated and stricter.")


if __name__ == "__main__":
    main()
