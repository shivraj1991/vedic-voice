"""End-to-end: build the synthetic set, score it, write results and review page."""

import json

from spike.eval import run
from spike.manifest import load
from spike.synthetic_set import build
from tests.conftest import FIXTURE


def test_synthetic_pipeline(tmp_path):
    manifest_path = build(FIXTURE, tmp_path / "set")
    m = load(manifest_path)
    assert m.ref_license and len(m.attempts) >= 20
    report = run(manifest_path, "dtw", tmp_path / "set")
    assert json.loads((tmp_path / "set" / "results.json").read_text())["metrics"]["words"] > 0
    html = (tmp_path / "set" / "review.html").read_text()
    assert "<audio" in html and "dhīmahi" in html
    # Guard rails the DTW scorer must keep on synthetic data.
    assert report["metrics"]["false_alarm_rate"] <= 0.05
    assert report["metrics"]["neutral_min_overall"] >= 90
