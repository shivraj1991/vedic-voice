"""Deterministic word split + morphology candidates for a shloka.

Content rule: grammar comes from rule-based tooling, never from an LLM, and
nothing reaches learners before an advisor verifies it. This module therefore
*proposes*; it never decides:

- Word split (pada): taken from a traditional pada-pāṭha when the corpus has one
  (Ṛgveda), otherwise proposed by Vidyut's segmenter (`split_source` records which).
- Morphology: every analysis Vidyut's lexicon (kosha) knows for the pada is listed
  as a candidate; the advisor picks one in the console. `proposed` is only a
  default (the segmenter's in-context choice when available).

Vidyut (MIT, ambuda.org) is a Pāṇinian Sanskrit toolkit. Its lexicon covers
classical Sanskrit well and Vedic forms poorly; unknown padas get status "unknown"
and must be analysed by the advisor.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from functools import cached_property
from pathlib import Path

from vidyut.cheda import Chedaka
from vidyut.kosha import Kosha
from vidyut.lipi import Scheme, transliterate

TOOL = "vidyut"
TOOL_VERSION = "0.4.0"

CASES = {
    "Prathama": "nominative", "Dvitiya": "accusative", "Trtiya": "instrumental",
    "Caturthi": "dative", "Panchami": "ablative", "Sasthi": "genitive",
    "Saptami": "locative", "Sambodhana": "vocative",
}  # fmt: skip
NUMBERS = {"Eka": "singular", "Dvi": "dual", "Bahu": "plural"}
GENDERS = {"Pum": "masculine", "Stri": "feminine", "Napumsaka": "neuter"}
PERSONS = {"Prathama": "3rd person", "Madhyama": "2nd person", "Uttama": "1st person"}
LAKARAS = {
    "Lat": "present", "Lit": "perfect", "Lut": "periphrastic future", "Lrt": "future",
    "Let": "subjunctive", "Lot": "imperative", "Lan": "imperfect", "VidhiLin": "optative",
    "AshirLin": "benedictive", "Lun": "aorist", "Lrn": "conditional",
}  # fmt: skip
VOICES = {"Kartari": "active", "Karmani": "passive", "Bhave": "impersonal"}


def to_slp1(iast: str) -> str:
    return transliterate(iast, Scheme.Iast, Scheme.Slp1)


def to_iast(slp1: str) -> str:
    return transliterate(slp1, Scheme.Slp1, Scheme.Iast)


def _name(enum_value) -> str | None:
    return None if enum_value is None else getattr(enum_value, "name", str(enum_value))


@dataclass(frozen=True)
class Analysis:
    """One morphological reading of a pada (maps onto `word_analyses.morphology`)."""

    kind: str  # subanta (noun-like) | tinanta (finite verb) | avyaya (indeclinable)
    lemma: str  # IAST stem or root
    root: str | None = None  # IAST dhātu for verbs and verbal derivatives
    derivation: str | None = None  # krt suffix for participles/derivatives
    case: str | None = None
    number: str | None = None
    gender: str | None = None
    person: str | None = None
    tense_mood: str | None = None
    voice: str | None = None

    @property
    def label(self) -> str:
        """Plain-English summary shown to the advisor, e.g. 'deva (m.) genitive singular'."""
        if self.kind == "avyaya":
            return f"{self.lemma} (indeclinable)"
        if self.kind == "tinanta":
            bits = [self.tense_mood, self.voice, self.person, self.number]
            return f"√{self.root} " + " ".join(b for b in bits if b)
        g = f" ({self.gender[0]}.)" if self.gender else ""
        d = f" from √{self.root} +{self.derivation}" if self.root else ""
        return f"{self.lemma}{g}{d} {self.case} {self.number}".strip()


@dataclass
class PadaDraft:
    surface: str  # as written/recited in the shloka line (IAST)
    pada: str  # the separated word (IAST)
    split_source: str  # padapatha | vidyut | given
    members: list[str] = field(default_factory=list)  # compound members if marked
    candidates: list[Analysis] = field(default_factory=list)
    proposed: int | None = None  # index into candidates
    word_index: int | None = None  # position of `surface` in the recited line (0-based)

    @property
    def status(self) -> str:
        if not self.candidates:
            return "unknown"
        return "unique" if len(self.candidates) == 1 else "ambiguous"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status
        d["candidates"] = [asdict(c) | {"label": c.label} for c in self.candidates]
        return d


def _analysis(entry) -> Analysis:
    if hasattr(entry, "dhatu_entry") and hasattr(entry, "purusha"):  # tinanta
        root = to_iast(entry.dhatu_entry.clean_text)
        return Analysis(
            kind="tinanta",
            lemma=root,
            root=root,
            person=PERSONS.get(_name(entry.purusha)),
            number=NUMBERS.get(_name(entry.vacana)),
            tense_mood=LAKARAS.get(_name(entry.lakara), _name(entry.lakara)),
            voice=VOICES.get(_name(entry.prayoga)),
        )
    pe = entry.pratipadika_entry
    root = derivation = None
    if hasattr(pe, "dhatu_entry"):
        root = to_iast(pe.dhatu_entry.clean_text)
        derivation = _name(pe.krt)
        lemma = to_iast(pe.lemma) if pe.lemma else root
    else:
        lemma = to_iast(pe.pratipadika.text)
    if pe.is_avyaya or entry.is_avyaya:
        return Analysis(kind="avyaya", lemma=lemma)
    return Analysis(
        kind="subanta",
        lemma=lemma,
        root=root,
        derivation=derivation,
        case=CASES.get(_name(entry.vibhakti)),
        number=NUMBERS.get(_name(entry.vacana)),
        gender=GENDERS.get(_name(entry.linga)),
    )


def _rank(a: Analysis) -> tuple:
    # Defaults an advisor most often confirms: indeclinables first (the lexicon also
    # declines "eva" as a noun), vocatives last, plain stems before derivations from
    # roots (it derives "deva" from √div too). Python's sort is stable otherwise.
    return (
        a.kind != "avyaya",
        a.case == "vocative",
        a.root is not None and a.kind == "subanta",
    )


def _lookup_keys(pada_iast: str) -> list[str]:
    """Kosha keys are pre-pausa SLP1 forms: final visarga is stored as s or r."""
    slp = to_slp1(pada_iast)
    keys = [slp]
    if slp.endswith("H"):
        keys += [slp[:-1] + "s", slp[:-1] + "r"]
    if slp.endswith("M"):
        keys.append(slp[:-1] + "m")
    return keys


_PP_ITI = re.compile(r"\s+iti$")


def parse_padapatha(line: str) -> list[tuple[str, list[str]]]:
    """Split a GRETIL Ṛgveda pada-pāṭha line into (pada, compound members).

    Format: words separated by " | ", compound members joined by "-", "--" for
    repetition (āmreḍita), " iti" after pragṛhya words, verse marker "// rv_... //".
    """
    line = re.sub(r"//.*$", "", line)
    line = re.sub(r"^-rv_\S+-\s*(\(rv_[^)]*\)\s*)?", "", line.strip())
    out = []
    for raw in line.split("|"):
        w = _PP_ITI.sub("", raw.strip())
        if not w:
            continue
        members = [m for m in re.split(r"-+", w) if m]
        out.append(("".join(members), members if len(members) > 1 else []))
    return out


class Toolkit:
    """Lazily loads Vidyut data (kosha ~ 1 s, segmenter ~ 1 s)."""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)

    @cached_property
    def kosha(self) -> Kosha:
        return Kosha(str(self.data_dir / "kosha"))

    @cached_property
    def chedaka(self) -> Chedaka:
        return Chedaka(str(self.data_dir))

    def lookup(self, pada_iast: str) -> list[Analysis]:
        """All lexicon analyses of a pada, de-duplicated, plain stems first."""
        seen: dict[Analysis, None] = {}
        for key in _lookup_keys(pada_iast):
            for entry in self.kosha.get(key):
                seen.setdefault(_analysis(entry), None)
        return sorted(seen, key=_rank)

    def segment(self, text_iast: str) -> list[tuple[str, Analysis | None]]:
        """Segmenter proposal: [(pada IAST, in-context analysis or None)]."""
        out = []
        slp = to_slp1(text_iast.lower())
        # The segmenter accepts SLP1 letters and spaces only; drop punctuation/accents.
        slp = re.sub(r"[^A-Za-z ]", "", slp)
        for tok in self.chedaka.run(slp):
            pada = to_iast(tok.text)
            pada = re.sub(r"[sr]$", "ḥ", pada) if tok.data is not None else pada
            out.append((pada, _analysis(tok.data) if tok.data is not None else None))
        return out

    def draft_line(self, text_iast: str, padapatha: str | None = None) -> list[PadaDraft]:
        """Draft analysis of one recited line.

        With a pada-pāṭha the split is traditional; otherwise each space-separated
        surface word is segmented by Vidyut (which also splits internal sandhi).
        """
        drafts: list[PadaDraft] = []
        if padapatha:
            for pada, members in parse_padapatha(padapatha):
                cands = self.lookup(pada)
                if not cands and members and all(self.lookup(m) for m in members):
                    # "urvārukam-iva": the hyphen joins separate words (iva, ca, ...),
                    # not compound members, since each member is an inflected form itself.
                    for m in members:
                        mc = self.lookup(m)
                        drafts.append(PadaDraft(pada, m, "padapatha", [], mc, 0))
                    continue
                if not cands and members:  # compound absent from the lexicon: head only
                    cands = self.lookup(members[-1])
                drafts.append(
                    PadaDraft(pada, pada, "padapatha", members, cands, 0 if cands else None)
                )
            surfaces = text_iast.split()
            if surfaces:  # link padas to the recited (saṃhitā) words they come from
                for d, owner in zip(
                    drafts, _assign(surfaces, [d.pada for d in drafts]), strict=True
                ):
                    d.surface, d.word_index = surfaces[owner], owner
            return drafts
        surfaces = text_iast.split()
        for owner, pada, source in self.split(text_iast):
            cands = self.lookup(pada)
            # The segmenter's in-context reading is often implausible (vocative "tat"),
            # so the default is the top-ranked candidate; it is only a starting point.
            drafts.append(
                PadaDraft(surfaces[owner], pada, source, [], cands, 0 if cands else None, owner)
            )
        return drafts

    def split(self, text_iast: str, conservative: bool = True) -> list[tuple[int, str, str]]:
        """Split a line into padas: [(surface word index, pada, split_source)].

        The segmenter sees the whole line (sandhi between words needs context). With
        `conservative`, a written word that is itself a known lexicon form is kept
        whole: Vidyut 0.4 over-splits (saṃyuge -> sam + yuge), and an unneeded split
        is worse for learners than a missed one, which the advisor adds.
        """
        # Avagraha (') marks an elided initial a. Undo the sandhi that caused it:
        # "saṅgo 'stv" = saṅgaḥ astu (-aḥ a- -> -o '-); "te 'pi" = te api.
        text_iast = re.sub(r"o(\s+)['’ऽ]", r"aḥ\1a", text_iast)
        text_iast = re.sub(r"(^|\s)['’ऽ]", r"\1a", text_iast)
        surfaces = text_iast.split()
        segs = [p for p, _ in self.segment(text_iast)]
        owners = _assign(surfaces, segs)
        out: list[tuple[int, str, str]] = []
        for i, surface in enumerate(surfaces):
            mine = [p for p, o in zip(segs, owners, strict=True) if o == i]
            whole = re.sub(r"[^\w]", "", surface)
            if not mine or (conservative and len(mine) > 1 and self.lookup(_pausa(whole))):
                out.append((i, _pausa(whole), "given"))
                continue
            for p in mine:
                out.append((i, p, "given" if p == surface else "vidyut"))
        return out


def _pausa(word: str) -> str:
    """Word-final sandhi back to pausa form for lexicon lookup (devo -> devaḥ is not
    attempted; only the unambiguous r/s -> ḥ)."""
    return re.sub(r"[rs]$", "ḥ", word)


def _assign(surfaces: list[str], padas: list[str]) -> list[int]:
    """Map each segmented pada to the surface word it came from.

    The segmenter works on the whole line and reports no offsets. We split the
    pada sequence into len(surfaces) consecutive, non-empty groups whose letter
    counts best match the surface words (dynamic programming). Sandhi changes
    lengths by a letter or two, which this tolerates; the advisor reviews anyway.
    """
    n, m = len(padas), len(surfaces)
    if n == 0:
        return []
    if m == 0 or n < m:  # segmenter merged words: attach by order
        return [min(i, max(m - 1, 0)) for i in range(n)]
    plen = [len(to_slp1(p)) for p in padas]
    slen = [len(to_slp1(s)) for s in surfaces]
    inf = float("inf")
    # best[i][j]: cost of covering the first i padas with the first j surfaces
    best = [[inf] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for j in range(1, m + 1):
        for i in range(j, n - (m - j) + 1):
            for k in range(j - 1, i):  # padas k..i-1 belong to surface j-1
                c = best[k][j - 1] + abs(sum(plen[k:i]) - slen[j - 1])
                if c < best[i][j]:
                    best[i][j], back[i][j] = c, k
    owners = [0] * n
    i = n
    for j in range(m, 0, -1):
        k = back[i][j]
        for t in range(k, i):
            owners[t] = j - 1
        i = k
    return owners
