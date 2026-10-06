"""Devanagari -> IAST transliteration (deterministic, rule-based).

Scoring works on IAST. Content is stored in both scripts, but test corpora (e.g.
Su-śrotā) ship Devanagari only, so the spike needs this direction. Vedic accent
marks and other signs we do not score are dropped.
"""

from __future__ import annotations

import unicodedata

_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ṅ",
    "च": "c", "छ": "ch", "ज": "j", "झ": "jh", "ञ": "ñ",
    "ट": "ṭ", "ठ": "ṭh", "ड": "ḍ", "ढ": "ḍh", "ण": "ṇ",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "ळ": "ḷ",
    "श": "ś", "ष": "ṣ", "स": "s", "ह": "h",
}  # fmt: skip
_VOWELS = {
    "अ": "a", "आ": "ā", "इ": "i", "ई": "ī", "उ": "u", "ऊ": "ū",
    "ऋ": "ṛ", "ॠ": "ṝ", "ऌ": "ḷ", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
}  # fmt: skip
_SIGNS = {
    "ा": "ā", "ि": "i", "ी": "ī", "ु": "u", "ू": "ū", "ृ": "ṛ", "ॄ": "ṝ",
    "ॢ": "ḷ", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
}  # fmt: skip
_VIRAMA = "्"
_OTHER = {"ं": "ṃ", "ँ": "ṃ", "ः": "ḥ", "ऽ": "'", "ॐ": "oṃ", "।": "|", "॥": "||"}
_DROP = {"़", "॑", "॒", "᳚", "᳛", "‌", "‍"}


def deva_to_iast(text: str) -> str:
    """Transliterate Devanagari to IAST; non-Devanagari characters pass through."""
    text = unicodedata.normalize("NFC", text)
    out: list[str] = []
    pending_a = False  # a consonant was emitted and still carries its inherent "a"
    for ch in text:
        if ch in _DROP:
            continue
        if ch in _CONSONANTS:
            if pending_a:
                out.append("a")
            out.append(_CONSONANTS[ch])
            pending_a = True
            continue
        if ch in _SIGNS:
            out.append(_SIGNS[ch])
            pending_a = False
            continue
        if ch == _VIRAMA:
            pending_a = False
            continue
        if pending_a:
            out.append("a")
            pending_a = False
        if ch in _VOWELS:
            out.append(_VOWELS[ch])
        elif ch in _OTHER:
            out.append(_OTHER[ch])
        elif "०" <= ch <= "९":
            out.append(str(ord(ch) - ord("०")))
        else:
            out.append(ch)
    if pending_a:
        out.append("a")
    return "".join(out)
