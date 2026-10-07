"""The committed seed files (shlokas/*.yaml) are consistent and safe to load."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCES = yaml.safe_load((ROOT / "sources.yaml").read_text("utf-8"))
SOURCE_IDS = {e["id"] for section in SOURCES.values() for e in section}
SEEDS = {p.stem: yaml.safe_load(p.read_text("utf-8")) for p in (ROOT / "shlokas").glob("*.yaml")}


def test_ten_mvp_shlokas_present():
    assert len(SEEDS) == 10


def test_every_seed_is_unverified_and_sourced():
    for slug, doc in SEEDS.items():
        assert doc["slug"] == slug
        assert doc["verified"] is False
        if doc["status"] == "draft":
            assert doc["source_id"] in SOURCE_IDS, slug
            assert doc["iast"] and doc["devanagari"] and doc["source_ref"]
        else:
            assert doc["status"] == "source_pending" and "iast" not in doc


def test_words_and_analyses_line_up():
    for slug, doc in SEEDS.items():
        if doc["status"] != "draft":
            continue
        words = doc["words"]
        assert [w["position"] for w in words] == list(range(len(words)))
        assert " ".join(w["surface_iast"] for w in words) == doc["iast"], slug
        positions = [a["word_position"] for a in doc["analyses"]]
        assert positions == sorted(positions), slug  # padas in recitation order
        assert set(positions) == set(range(len(words))), slug  # every word analysed
        for a in doc["analyses"]:
            m = a["morphology"]
            assert m["split_source"] in {"padapatha", "vidyut", "given"}
            assert m["proposed"] is None or m["proposed"] in m["candidates"]
