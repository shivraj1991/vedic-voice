from spike.eval_dcs import f1, norm, parse_gold


def test_parse_gold_merges_compound_members_and_sandhi_groups():
    morph = (
        "mārgasatyaṃ____2-3 mārga_N__2 satyam_N_NNeS_3 trividhaṃ_A_NNeS_4 "
        "cāpyasaṃskṛtam____5-7 ca_C__5 api_T__6 asaṃskṛtam_A_NNeS_7"
    )
    words = parse_gold(morph)
    assert [w["form"] for w in words] == ["mārgasatyam", "trividhaṃ", "ca", "api", "asaṃskṛtam"]
    assert words[0]["compound"] and not words[1]["compound"]


def test_norm_and_f1():
    assert norm("kleśais") == norm("kleśaiḥ") == "kleśaiḥ"
    assert norm("samaṃ") == "samam"
    assert f1(["a", "b"], ["a", "b"]) == 1.0
    assert f1(["a", "b"], ["c"]) == 0.0
