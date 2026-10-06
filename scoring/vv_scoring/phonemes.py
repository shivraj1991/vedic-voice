"""Deterministic IAST → phoneme tokenizer.

IAST maps almost one-to-one onto Sanskrit sounds, so a small rule table is
enough and stays auditable. No ML is involved. The phone labels are IAST
tokens; attributes (vowel length, aspiration, retroflex) drive issue messages.
"""

import unicodedata
from dataclasses import dataclass

# Longest tokens first so "kh" wins over "k" and "ai" over "a".
_VOWELS_LONG = ["ai", "au", "ā", "ī", "ū", "ṝ", "ḹ", "e", "o"]
_VOWELS_SHORT = ["a", "i", "u", "ṛ", "ḷ"]
_ASPIRATED = ["kh", "gh", "ch", "jh", "ṭh", "ḍh", "th", "dh", "ph", "bh"]
_CONSONANTS = list("kgcjtdpbnmyrlvsh") + ["ṅ", "ñ", "ṭ", "ḍ", "ṇ", "ś", "ṣ"]
_SPECIAL = {"ṃ": "anusvara", "ḥ": "visarga", "m̐": "anusvara"}
_RETROFLEX = {"ṭ", "ṭh", "ḍ", "ḍh", "ṇ", "ṣ", "ṛ", "ṝ"}

_TOKENS = sorted(
    _VOWELS_LONG + _VOWELS_SHORT + _ASPIRATED + _CONSONANTS + list(_SPECIAL),
    key=len,
    reverse=True,
)


@dataclass(frozen=True)
class Phone:
    label: str
    kind: str  # "vowel" | "consonant" | "anusvara" | "visarga"
    long: bool = False
    aspirated: bool = False
    retroflex: bool = False


def normalize_iast(text: str) -> str:
    """NFC-normalize, lowercase, and fold common variant spellings."""
    text = unicodedata.normalize("NFC", text.strip().lower())
    return text.replace("ṁ", "ṃ").replace("ṟ", "r")


def tokenize(word: str) -> list[Phone]:
    """Split one IAST word into phones. Raises ValueError on unknown characters."""
    s = normalize_iast(word)
    phones: list[Phone] = []
    i = 0
    while i < len(s):
        if s[i] in " -'’":
            i += 1
            continue
        for tok in _TOKENS:
            if s.startswith(tok, i):
                phones.append(_make_phone(tok))
                i += len(tok)
                break
        else:
            raise ValueError(f"unknown IAST character {s[i]!r} in {word!r}")
    return phones


def _make_phone(tok: str) -> Phone:
    if tok in _SPECIAL:
        return Phone(tok, _SPECIAL[tok])
    if tok in _VOWELS_LONG or tok in _VOWELS_SHORT:
        return Phone(tok, "vowel", long=tok in _VOWELS_LONG, retroflex=tok in _RETROFLEX)
    return Phone(tok, "consonant", aspirated=tok in _ASPIRATED, retroflex=tok in _RETROFLEX)


def long_vowels(word: str) -> list[str]:
    """Long vowels in a word, in order (used to phrase 'hold the vowel' advice)."""
    return [p.label for p in tokenize(word) if p.kind == "vowel" and p.long]
