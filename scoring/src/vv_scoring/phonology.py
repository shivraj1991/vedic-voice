"""IAST -> Sanskrit phoneme units -> acoustic-model token sets.

This is deterministic, rule-based phonology (no ML): a Sanskrit text in IAST is
split into phoneme units (a, ā, kh, ṭ, ś, ...). Each unit is mapped to the *set*
of model tokens that count as a correct realisation of it, because the espeak
IPA inventory the model was trained on has several near-equivalent symbols
(e.g. short a may surface as ə or ɐ).

Each unit also has a confusion list: the specific mistakes we test for and can
explain in plain language (ā said short, retroflex ṭ said as dental t, ś said as
s, aspiration dropped, ...). Restricting GOP to these curated alternatives keeps
feedback actionable and avoids blaming learners for model noise.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# --- Inventory -------------------------------------------------------------
# Accepted realisations of each Sanskrit unit, in model (espeak IPA) tokens.
# A realisation is space-separated slots; each slot lists alternative tokens
# with "|". Example: "d|d̪ h|ɦ" = a d-like token followed by an h-like token.
# Sets are deliberately broad: learners are only blamed when a *curated*
# alternative (see CONFUSIONS) fits clearly better, relative to the reference
# reciter. Tokens absent from the model vocabulary are dropped at load time.
_A = "ə|ɐ|ʌ|a|ɑ"
_I = "ɪ|i|ᵻ|ɨ"
_U = "ʊ|u"
_ECHO = "ə|ɐ|a|ɪ|i|ʊ|u|e|o"


def _asp(base: str, single: str) -> tuple[str, ...]:
    return (single, f"{base} h|ɦ")


ACCEPT: dict[str, tuple[str, ...]] = {
    # vowels
    "a": (_A,),
    "ā": ("aː|ɑː|a|ä|ɑ|a.ː",),
    "i": (_I,),
    "ī": ("iː|i|iːː",),
    "u": (_U,),
    "ū": ("uː|u",),
    # Modern recitation realises ṛ as "ri"/"ru"; accept these rather than flag them.
    "ṛ": ("r̩", f"ɾ|r|ɹ {_I}|{_U}", "ɾ|r|ɹ"),
    "ṝ": ("r̩", "ɾ|r|ɹ iː|i"),
    "ḷ": ("l̩|l|ɭ|ɾ|r|ɽ", "l|ɭ ɪ|i"),
    "e": ("eː|e|ɛ|e̞|ɛː",),
    "ai": ("ai|aɪ|əɪ|ɛː|ɛ", f"{_A} {_I}"),
    "o": ("oː|o|ɔ|o̞|ɔː",),
    "au": ("au|aʊ|əʊ|ɔː", f"{_A} {_U}"),
    # velars
    "k": ("k|kː|c",),
    "kh": _asp("k|kː", "kʰ|kh|x"),
    "g": ("ɡ|ɡː|ɡʲ",),
    "gh": _asp("ɡ", "ɡʰ"),
    "ṅ": ("ŋ|n",),
    # palatals
    "c": ("tʃ|tɕ|c|tʃː",),
    "ch": _asp("tʃ|tɕ|c", "tʃʰ|tɕh|cʰ"),
    "j": ("dʒ|dʑ|ɟ|dʒː|ʒ",),
    "jh": _asp("dʒ|dʑ|ɟ", "ɟʰ"),
    "ñ": ("ɲ|n|nʲ",),
    # "jñ" is one cluster with several accepted modern pronunciations (jña, gya, dnya).
    "jñ": ("dʒ|dʑ|ɟ ɲ|n|nʲ", "ɡ j", "ɡ ɲ|n", f"dʒ|dʑ {_I}|{_A} n|ɲ", "d n j"),
    # retroflexes: strict sets, so a dental realisation can be detected
    "ṭ": ("ʈ|ʈʰ",),
    "ṭh": _asp("ʈ", "ʈʰ"),
    "ḍ": ("ɖ|ɽ",),
    "ḍh": _asp("ɖ|ɽ", "ɖʰ"),
    "ṇ": ("ɳ|ɽ",),
    # dentals
    "t": ("t̪|t|tː|t̪ː",),
    "th": _asp("t̪|t", "tʰ|th"),
    "d": ("d|d̪|dː|ð",),
    "dh": _asp("d|d̪", "dʰ|dʰː"),
    "n": ("n|n̩|nʲ",),
    # labials
    "p": ("p|pː",),
    "ph": _asp("p", "pʰ|ph|f|ɸ"),
    "b": ("b|bː",),
    "bh": _asp("b", "bʰ"),
    "m": ("m|mʲ",),
    # semivowels, sibilants, h
    "y": ("j",),
    "r": ("ɾ|r|ɹ|ɽ|ʁ|r̩",),
    "l": ("l|ɫ|ɭ|lː",),
    "v": ("ʋ|v|w|β|vʲ",),
    "ś": ("ʃ|ɕ|ç|ʂ",),
    "ṣ": ("ʂ|ʃ|ɕ",),
    "s": ("s|s̪|sʲ",),
    "h": ("h|ɦ|x",),
    # anusvāra: homorganic nasal or nasalised vowel
    "ṃ": ("m|n|ŋ|ɳ|ɲ|ã|ẽ|ĩ|õ|ũ|ɑ̃|ɛ̃|ɔ̃|ɐ̃",),
    # visarga: breath, often with an echo of the preceding vowel ("viṣṇuḥ" -> "viṣṇuhu")
    "ḥ": ("h|x|ç|f", f"h|x|ç {_ECHO}"),
}

VOWELS = frozenset(["a", "ā", "i", "ī", "u", "ū", "ṛ", "ṝ", "ḷ", "e", "ai", "o", "au"])
LONG_VOWELS = frozenset(["ā", "ī", "ū", "ṝ", "e", "ai", "o", "au"])

# Plain-language issue for each (expected unit -> heard unit/None) confusion.
# None means the sound was skipped.
Issue = tuple[str, str]  # (issue_code, template). Template fields: {exp}, {heard}, {word}

_LEN = (
    "vowel_length_short",
    'hold the long "{exp}" for two beats; it sounded short like "{heard}"',
)
_LEN_L = ("vowel_length_long", 'keep "{exp}" short (one beat); it sounded long like "{heard}"')
_ASP_MISSING = ("aspiration_missing", 'add a breath after "{exp}"; it sounded like plain "{heard}"')
_ASP_EXTRA = ("aspiration_extra", '"{exp}" has no breath after it; it sounded like "{heard}"')
_RETRO_MISSING = (
    "retroflex_missing",
    'curl the tongue tip back for "{exp}"; it sounded like dental "{heard}"',
)
_RETRO_EXTRA = (
    "retroflex_extra",
    'touch the teeth for "{exp}" (dental); it sounded like retroflex "{heard}"',
)
_SIB = ("sibilant", 'say "{exp}", not "{heard}"')
_NASAL = ("nasal", 'the nasal "{exp}" sounded like "{heard}"')
_VOWEL = ("vowel_quality", 'the vowel "{exp}" sounded like "{heard}"')
_MISSING = ("sound_missing", 'the "{exp}" sound was not heard')
_OTHER = ("sound_changed", '"{exp}" sounded like "{heard}"')

CONFUSIONS: dict[str, dict[str | None, Issue]] = {
    "a": {"ā": _LEN_L, None: _MISSING},
    "ā": {"a": _LEN, None: _MISSING},
    "i": {"ī": _LEN_L, "e": _VOWEL, None: _MISSING},
    "ī": {"i": _LEN, None: _MISSING},
    "u": {"ū": _LEN_L, "o": _VOWEL, None: _MISSING},
    "ū": {"u": _LEN, None: _MISSING},
    "e": {"i": _VOWEL, "ai": _VOWEL, None: _MISSING},
    "o": {"u": _VOWEL, "au": _VOWEL, None: _MISSING},
    "ai": {"e": _VOWEL, None: _MISSING},
    "au": {"o": _VOWEL, None: _MISSING},
    "k": {"kh": _ASP_EXTRA, None: _MISSING},
    "kh": {"k": _ASP_MISSING, None: _MISSING},
    "g": {"gh": _ASP_EXTRA, None: _MISSING},
    "gh": {"g": _ASP_MISSING, None: _MISSING},
    "c": {"ch": _ASP_EXTRA, None: _MISSING},
    "ch": {"c": _ASP_MISSING, None: _MISSING},
    "j": {"jh": _ASP_EXTRA, None: _MISSING},
    "jh": {"j": _ASP_MISSING, None: _MISSING},
    "ṭ": {"t": _RETRO_MISSING, "ṭh": _ASP_EXTRA, None: _MISSING},
    "ṭh": {"ṭ": _ASP_MISSING, "th": _RETRO_MISSING, None: _MISSING},
    "ḍ": {"d": _RETRO_MISSING, "ḍh": _ASP_EXTRA, None: _MISSING},
    "ḍh": {"ḍ": _ASP_MISSING, "dh": _RETRO_MISSING, None: _MISSING},
    "ṇ": {"n": _RETRO_MISSING, None: _MISSING},
    "t": {"ṭ": _RETRO_EXTRA, "th": _ASP_EXTRA, None: _MISSING},
    "th": {"t": _ASP_MISSING, None: _MISSING},
    "d": {"ḍ": _RETRO_EXTRA, "dh": _ASP_EXTRA, None: _MISSING},
    "dh": {"d": _ASP_MISSING, "ḍh": _RETRO_EXTRA, None: _MISSING},
    "n": {"ṇ": _RETRO_EXTRA, None: _MISSING},
    "p": {"ph": _ASP_EXTRA, None: _MISSING},
    "ph": {"p": _ASP_MISSING, None: _MISSING},
    "b": {"bh": _ASP_EXTRA, None: _MISSING},
    "bh": {"b": _ASP_MISSING, None: _MISSING},
    "ś": {"s": _SIB, None: _MISSING},
    "ṣ": {"s": _SIB, None: _MISSING},
    "s": {"ś": _SIB, None: _MISSING},
    "v": {"b": _OTHER, None: _MISSING},
    "y": {"j": _OTHER, None: _MISSING},
    "ñ": {None: _MISSING},
    "ṅ": {None: _MISSING},
    "m": {"n": _NASAL, None: _MISSING},
    "ṃ": {None: _MISSING},
    "ḥ": {None: ("visarga_missing", 'the final breath "ḥ" was not heard')},
    "h": {None: _MISSING},
    "r": {None: _MISSING},
    "l": {None: _MISSING},
}

# Multi-character IAST units (checked before single characters).
_MULTI = ("jñ", "kh", "gh", "ch", "jh", "ṭh", "ḍh", "th", "dh", "ph", "bh", "ai", "au")
_SINGLE = set(ACCEPT) - set(_MULTI)
_ALIASES = {"ṁ": "ṃ", "ḹ": "ḷ", "ḻ": "ḷ", "ē": "e", "ō": "o", "ṉ": "n"}
_IGNORED = re.compile(r"[\s|।॥'’ʼ\-.,;:!?\"()\[\]0-9०-९]+")


@dataclass(frozen=True)
class Unit:
    """One Sanskrit phoneme in a word. `long` marks a geminate consonant (tt, mm)."""

    symbol: str
    long: bool = False


@dataclass(frozen=True)
class Word:
    """A word (pada as recited) and its phoneme units."""

    text: str
    units: tuple[Unit, ...] = field(default_factory=tuple)


class PhonologyError(ValueError):
    """Raised for IAST input we cannot tokenise."""


def _normalise(text: str) -> str:
    # NFC keeps IAST letters precomposed; then drop any leftover combining marks
    # (Vedic accents such as udātta acute / svarita) which we do not score.
    text = unicodedata.normalize("NFC", text.lower())
    text = "".join(_ALIASES.get(ch, ch) for ch in text)
    decomposed = unicodedata.normalize("NFD", text)
    kept = []
    for ch in decomposed:
        if unicodedata.combining(ch) and ch not in "̣̄̇́̃":
            continue
        kept.append(ch)
    text = unicodedata.normalize("NFC", "".join(kept))
    # Acute on vowels (accent marks) survive NFC as precomposed á, í ... -> strip.
    return text.translate(str.maketrans("áíúéóàìùèò", "aiueoaiueo"))


def tokenize_word(word: str) -> tuple[Unit, ...]:
    """Split one IAST word into phoneme units, merging geminate consonants."""
    w = _IGNORED.sub("", _normalise(word))
    raw: list[str] = []
    i = 0
    while i < len(w):
        two = w[i : i + 2]
        if two in _MULTI:
            raw.append(two)
            i += 2
        elif w[i] in _SINGLE:
            raw.append(w[i])
            i += 1
        else:
            raise PhonologyError(f"unsupported character {w[i]!r} in {word!r}")
    units: list[Unit] = []
    for sym in raw:
        prev = units[-1] if units else None
        # Geminates: "tt", "mm", and aspirate clusters "tth" / "ddh" (unaspirated + aspirated
        # of the same place) are one long consonant acoustically.
        same_place = prev is not None and (
            prev.symbol == sym or (len(sym) == 2 and sym[1] == "h" and prev.symbol == sym[0])
        )
        if prev and same_place and sym not in VOWELS and not prev.long:
            units[-1] = Unit(sym, long=True)
            continue
        units.append(Unit(sym))
    return tuple(units)


def parse_text(text: str) -> list[Word]:
    """Split a recited line into words (on whitespace) and tokenise each."""
    words = []
    for raw in text.split():
        cleaned = _IGNORED.sub("", raw)
        if not cleaned:
            continue
        words.append(Word(text=raw.strip("|।॥,."), units=tokenize_word(raw)))
    if not words:
        raise PhonologyError("no words in text")
    return words


def realisations(symbol: str, vocab: dict[str, int]) -> tuple[tuple[tuple[int, ...], ...], ...]:
    """Accepted realisations of a unit (or of a space-separated unit sequence like "r i")
    as sequences of model token-id sets. Unknown tokens are dropped."""
    parts = symbol.split()
    if len(parts) > 1:
        seqs: list[tuple[tuple[int, ...], ...]] = [()]
        for part in parts:
            seqs = [a + b for a in seqs for b in realisations(part, vocab)]
        return tuple(seqs)
    if symbol not in ACCEPT:
        raise PhonologyError(f"unknown unit {symbol!r}")
    out = []
    for real in ACCEPT[symbol]:
        slots = []
        for slot in real.split():
            ids = tuple(vocab[t] for t in slot.split("|") if t in vocab)
            if not ids:
                break
            slots.append(ids)
        else:
            out.append(tuple(slots))
    if not out:
        raise PhonologyError(f"no model tokens for {symbol!r}")
    return tuple(out)


def alternatives(symbol: str) -> dict[str | None, Issue]:
    """Curated mistakes to test for this unit.

    Keys are a replacement unit, several space-separated units ("r i"), or None
    for deletion.
    """
    return CONFUSIONS.get(symbol, {None: _MISSING})
