"""Tests for the deterministic analysis helpers.

Pure functions are always tested; tests that need Vidyut's 32 MB data bundle
skip unless `uv run python -m spike.fetch` has been run.
"""

from pathlib import Path

import pytest

from vv_content.analysis import Analysis, Toolkit, _assign, _pausa, _rank, parse_padapatha

DATA = Path(__file__).resolve().parents[1] / "vendor" / "vidyut-0.4.0"
needs_data = pytest.mark.skipif(not (DATA / "kosha").exists(), reason="vidyut data not fetched")


def test_parse_padapatha_handles_compounds_iti_and_markers():
    line = (
        "-rv_1:1/1- (rv_1,1) agnim | īḷe | puraḥ-hitam | dyāvāpṛthivī iti | dive--dive "
        "// rv_1,1.1 //"
    )
    assert parse_padapatha(line) == [
        ("agnim", []),
        ("īḷe", []),
        ("puraḥhitam", ["puraḥ", "hitam"]),
        ("dyāvāpṛthivī", []),
        ("divedive", ["dive", "dive"]),
    ]


def test_assign_maps_padas_back_to_surface_words():
    surfaces = ["karmaṇy", "evādhikāras", "te", "mā"]
    padas = ["karmaṇi", "eva", "adhikāraḥ", "te", "mā"]
    assert _assign(surfaces, padas) == [0, 1, 1, 2, 3]


def test_assign_when_segmenter_merges_words():
    assert _assign(["a", "b", "c"], ["ab", "c"]) == [0, 1]


def test_pausa_restores_final_visarga_only():
    assert _pausa("gurur") == "guruḥ"
    assert _pausa("bhargas") == "bhargaḥ"
    assert _pausa("devo") == "devo"


def test_rank_prefers_indeclinables_and_avoids_vocatives():
    voc = Analysis("subanta", "eva", case="vocative", number="singular", gender="neuter")
    avy = Analysis("avyaya", "eva")
    nom = Analysis("subanta", "tad", case="nominative", number="singular", gender="neuter")
    assert sorted([voc, nom, avy], key=_rank) == [avy, nom, voc]


def test_labels_are_plain_english():
    a = Analysis("subanta", "deva", case="genitive", number="singular", gender="masculine")
    assert a.label == "deva (m.) genitive singular"
    v = Analysis("tinanta", "yaj", root="yaj", person="1st person", number="plural",
                 tense_mood="present", voice="active")  # fmt: skip
    assert v.label == "√yaj present active 1st person plural"


@needs_data
def test_lookup_lists_all_readings():
    tk = Toolkit(DATA)
    labels = [a.label for a in tk.lookup("devasya")]
    assert "deva (m.) genitive singular" in labels
    assert tk.lookup("dhīmahi") == []  # Vedic form: unknown, advisor must analyse


@needs_data
def test_padapatha_split_and_joined_particles():
    tk = Toolkit(DATA)
    line = "urvārukam-iva | bandhanāt // rv_7,59.12 //"
    drafts = tk.draft_line("", padapatha=line)
    assert [d.pada for d in drafts] == ["urvārukam", "iva", "bandhanāt"]
    assert all(d.split_source == "padapatha" for d in drafts)
    assert drafts[1].candidates[0].kind == "avyaya"


@needs_data
def test_conservative_split_keeps_known_words_whole():
    tk = Toolkit(DATA)
    padas = [p for _, p, _ in tk.split("kṛtvā ca saṃyuge")]
    assert padas == ["kṛtvā", "ca", "saṃyuge"]
    # ...but still undoes real sandhi between words
    padas = [p for _, p, _ in tk.split("karmaṇy evādhikāras te")]
    assert padas[:3] == ["karmaṇi", "eva", "adhikāraḥ"]


@needs_data
def test_avagraha_restores_elided_a():
    tk = Toolkit(DATA)
    padas = [p for _, p, _ in tk.split("saṅgo 'stv akarmaṇi")]
    assert "astu" in padas
