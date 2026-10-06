import json
from pathlib import Path

import pytest

from vv_scoring.phonology import (
    ACCEPT,
    CONFUSIONS,
    PhonologyError,
    parse_text,
    realisations,
    tokenize_word,
)


def syms(word: str) -> list[str]:
    return [u.symbol for u in tokenize_word(word)]


def test_aspirates_and_diphthongs_are_single_units():
    assert syms("bhargo") == ["bh", "a", "r", "g", "o"]
    assert syms("dhīmahi") == ["dh", "ī", "m", "a", "h", "i"]
    assert syms("naiṣkarmyaṃ") == ["n", "ai", "ṣ", "k", "a", "r", "m", "y", "a", "ṃ"]
    assert syms("saumya") == ["s", "au", "m", "y", "a"]


def test_jn_cluster_and_geminates():
    assert syms("yajñasya") == ["y", "a", "jñ", "a", "s", "y", "a"]
    units = tokenize_word("uttama")
    assert [(u.symbol, u.long) for u in units][1] == ("t", True)
    # unaspirated + aspirated of the same place is one long aspirate
    assert [(u.symbol, u.long) for u in tokenize_word("buddhi")][2] == ("dh", True)


def test_accents_and_variants_normalised():
    assert syms("agním") == syms("agnim")
    assert syms("saṁhitā") == syms("saṃhitā")
    assert syms("īḻe") == ["ī", "ḷ", "e"]


def test_parse_text_strips_punctuation():
    words = parse_text("tat savitur vareṇyaṃ | bhargo devasya dhīmahi ||")
    assert [w.text for w in words] == ["tat", "savitur", "vareṇyaṃ", "bhargo", "devasya", "dhīmahi"]


def test_unknown_character_rejected():
    with pytest.raises(PhonologyError):
        tokenize_word("xyz")


def test_confusions_reference_known_units():
    for unit, alts in CONFUSIONS.items():
        assert unit in ACCEPT
        for alt in alts:
            if alt is not None:
                for part in alt.split():
                    assert part in ACCEPT, (unit, alt)


def test_realisations_with_tiny_vocab(vocab):
    # dh = "dʰ" or "d" + "h"
    reals = realisations("dh", vocab)
    assert ((vocab["dʰ"],),) in [tuple(r) for r in reals] or any(
        len(r) == 1 and vocab["dʰ"] in r[0] for r in reals
    )
    assert any(len(r) == 2 for r in reals)


def test_every_unit_has_tokens_in_real_model_vocab():
    vocab_path = Path(__file__).parents[1] / "models" / "w2v2-xlsr53-espeak" / "vocab.json"
    if not vocab_path.exists():
        pytest.skip("model not downloaded")
    vocab = json.loads(vocab_path.read_text("utf-8"))
    for unit in ACCEPT:
        assert realisations(unit, vocab)
