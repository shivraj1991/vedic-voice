from vv_scoring.issues import describe


def test_skipped():
    assert describe("savitur", 0.1, 0.2)[0] == "skipped"


def test_too_short_names_the_long_vowel():
    code, text = describe("dhīmahi", 0.5, 0.9)
    assert code == "too_short"
    assert "'ī'" in text and "dhīmahi" in text


def test_too_short_without_long_vowel():
    code, text = describe("tat", 0.5, 0.9)
    assert code == "too_short" and "faster" in text


def test_too_long_and_mismatch():
    assert describe("tat", 2.0, 0.9)[0] == "too_long"
    assert describe("tat", 1.0, 0.2)[0] == "sound_mismatch"
