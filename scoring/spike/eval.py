"""Run a scorer over a labelled test set and report accuracy.

    uv run python -m spike.eval --synthetic                 # build + score synthetic set
    uv run python -m spike.eval --manifest path/manifest.yaml
    uv run python -m spike.eval --manifest m.yaml --scorer dtw

Writes <out>/results.json and <out>/review.html (open in a browser to listen).
"""

import argparse
import json
import time
from pathlib import Path

from spike import manifest as mf
from spike import metrics as mx
from spike import review
from vv_scoring.audio_io import load_audio
from vv_scoring.scorers.base import PASS_THRESHOLD
from vv_scoring.scorers.dtw import DtwScorer

HERE = Path(__file__).parent
SCORERS = {"dtw": DtwScorer}  # ctc-gop and whisper baseline register here


def run(
    manifest_path: Path, scorer_name: str, out_dir: Path, threshold: int = PASS_THRESHOLD
) -> dict:
    m = mf.load(manifest_path)
    scorer = SCORERS[scorer_name]()
    ref = load_audio(m.ref_audio)
    results, rows = [], []
    for att in m.attempts:
        y = load_audio(att.audio)
        t0 = time.perf_counter()
        r = scorer.score(ref, m.ref_marks, y, m.words)
        latency = time.perf_counter() - t0
        words = [
            {
                "position": w.position,
                "iast": w.iast,
                "score": w.score,
                "issue_code": w.issue_code,
                "issue_text": w.issue_text,
                "details": {k: round(v, 4) for k, v in w.details.items()},
            }
            for w in r.words
        ]
        results.append(
            {
                "id": att.id,
                "group": att.group,
                "overall": r.overall,
                "words": words,
                "latency_s": round(latency, 3),
            }
        )
        rows.append(
            {
                "labels": att.labels,
                "overall": r.overall,
                "rating": att.rating,
                "latency_s": latency,
                "scores": {w["position"]: w["score"] for w in words},
                "codes": {w["position"]: w["issue_code"] for w in words},
            }
        )
    metrics = mx.compute(rows, threshold).to_dict()
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "scorer": f"{scorer.name}@{scorer.version}",
        "threshold": threshold,
        "metrics": metrics,
        "attempts": results,
    }
    (out_dir / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), "utf-8")
    review.render(out_dir, m, results, metrics, report["scorer"], threshold)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--manifest", type=Path, help="labelled test-set manifest (YAML)")
    src.add_argument("--synthetic", action="store_true", help="build and use the synthetic set")
    ap.add_argument("--scorer", choices=sorted(SCORERS), default="dtw")
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--threshold", type=int, default=PASS_THRESHOLD)
    args = ap.parse_args()

    if args.synthetic:
        from spike.synthetic_set import build

        manifest_path = build(HERE / "fixtures" / "gayatri.yaml", args.out / "synthetic")
        out = args.out / "synthetic"
    else:
        manifest_path, out = args.manifest, args.out
    report = run(manifest_path, args.scorer, out, args.threshold)
    print(json.dumps(report["metrics"], indent=2))
    print(f"\nReview page: {out / 'review.html'}")


if __name__ == "__main__":
    main()
