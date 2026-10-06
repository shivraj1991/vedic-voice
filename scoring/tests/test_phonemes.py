import unicodedata

import pytest

from vv_scoring.phonemes import long_vowels, normalize_iast, tokenize


def labels(word):
    return [p.label for p in tokenize(word)]


def test_aspirated_consonants_are_single_phones():
    assert labels("bhargo") == ["bh", "a", "r", "g", "o"]
    assert tokenize("bhargo")[0].aspirated


def test_diphthongs_win_over_short_a():
    assert labels("aiśvarya") == ["ai", "ś", "v", "a", "r", "y", "a"]
    assert labels("gauḥ") == ["g", "au", "ḥ"]


def test_vowel_length_and_retroflex():
    ps = tokenize("vareṇyaṃ")
    assert [p.label for p in ps] == ["v", "a", "r", "e", "ṇ", "y", "a", "ṃ"]
    assert next(p for p in ps if p.label == "ṇ").retroflex
    assert next(p for p in ps if p.label == "e").long  # e/o are always long in Sanskrit
    assert ps[-1].kind == "anusvara"


def test_long_vowels():
    assert long_vowels("dhīmahi") == ["ī"]
    assert long_vowels("pracodayāt") == ["o", "ā"]
    assert long_vowels("tat") == []


def test_decomposed_unicode_and_variant_anusvara():
    nfd = unicodedata.normalize("NFD", "bhūr")
    assert labels(nfd) == ["bh", "ū", "r"]
    assert normalize_iast("oṁ") == "oṃ"


def test_unknown_character_raises():
    with pytest.raises(ValueError, match="unknown IAST"):
        tokenize("om7")
