"""Build the initial seed (data/shlokas/*.yaml) for the 10 MVP shlokas.

Each shloka's text is extracted from a recorded open-corpus source (see
data/sources.yaml), transliterated deterministically (Vidyut lipi), split into
recited words, and given *draft* word analyses (vv_content.analysis). Everything
is `verified: false`: the advisor reviews it in the console before learners
see it. After seeding, the DB is the source of truth (decision 2026-10-06);
these files only bootstrap it.

Wording is never "corrected" here. Known problems in a source (typos, variant
readings, missing source) go into `review_notes` for the advisor.

    uv run python -m vv_content.seed_build        # needs `python -m spike.fetch` first
"""

from __future__ import annotations

import argparse
import html
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from vidyut.lipi import Scheme, transliterate

from .analysis import TOOL, TOOL_VERSION, Toolkit

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "vendor"
OUT = ROOT / "shlokas"


def iast_to_deva(text: str) -> str:
    return transliterate(text, Scheme.Iast, Scheme.Devanagari)


def deva_to_iast(text: str) -> str:
    return transliterate(text, Scheme.Devanagari, Scheme.Iast)


def _read(name: str) -> str:
    path = VENDOR / name
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run `uv run python -m spike.fetch`")
    return path.read_text("utf-8", errors="replace")


def _clean_iast(text: str) -> str:
    """Drop verse markers/dandas, keep words and avagraha; ṁ -> ṃ (same anusvāra)."""
    text = text.replace("ṁ", "ṃ")
    text = re.sub(r"\|\||//|\||/|\.|,", " ", text)
    return " ".join(text.split())


def _clean_deva(text: str) -> str:
    """Wikisource Devanagari: ':' is often typed for visarga, 's' for avagraha."""
    text = re.sub(r"(?<=[ऀ-ॿ]):", "ः", text)
    text = re.sub(r"(?<=[ऀ-ॿ])s(?=[ऀ-ॿ])", "ऽ", text)
    text = re.sub(r"[।॥]+\s*[०-९0-9]*\s*[।॥]*", " ", text)
    return " ".join(text.split())


# --- extractors: each returns (iast text, pada-pāṭha line or None) ----------


def rv(ref: str) -> Callable[[], tuple[str, str | None]]:
    def get() -> tuple[str, str | None]:
        pp = _read("rv_padapatha.txt").splitlines()
        pada_line = next(line for line in pp if f"// {ref} //" in line)
        m, s, v = re.match(r"rv_(\d+),(\d+)\.(\d+)", ref).groups()
        key = f"RV_{int(m)},{int(s):03d}.{int(v):02d}"
        lines = _read("rv_samhita.txt").splitlines()
        end = next(i for i, line in enumerate(lines) if key in line)
        start = end
        while start > 0 and lines[start - 1].strip():
            start -= 1
        text = re.sub(r"RV_\S+", " ", " ".join(lines[start : end + 1]))
        return _clean_iast(text), pada_line

    return get


def bhg(ref: str) -> Callable[[], tuple[str, str | None]]:
    def get() -> tuple[str, str | None]:
        raw = html.unescape(re.sub(r"<[^>]+>", "", _read("bhagavadgita.htm")))
        parts = [
            line.split("Bhg_")[0]
            for line in raw.splitlines()
            if re.search(rf"Bhg_{re.escape(ref)}[ac]\b", line)
        ]
        return _clean_iast(" ".join(parts)), None

    return get


def gretil_lines(name: str, first: str, n_lines: int = 1) -> Callable[[], tuple[str, None]]:
    """Text starting at the first line that begins with `first` (n consecutive lines)."""

    def get() -> tuple[str, None]:
        lines = _read(name).splitlines()
        i = next(k for k, line in enumerate(lines) if line.strip().startswith(first))
        return _clean_iast(" ".join(lines[i : i + n_lines])), None

    return get


def bru_asato() -> tuple[str, None]:
    """The three yajus of BṛU 1.3.28 (the mantra portion only, not its explanation)."""
    line = next(x for x in _read("brhadaranyaka.txt").splitlines() if "brhup_1,3.28" in x)
    # The text quotes the mantra with "iti" fused by sandhi: "... gamayeti". Undo
    # exactly that (gamaya + iti -> gamayeti); recorded in review_notes.
    m = re.search(r"(asato mā sad gamaya.*?mṛtyor māmṛtaṃ gamay)eti", line)
    if not m:
        raise ValueError("BṛU 1.3.28 mantra not found")
    return _clean_iast(m.group(1) + "a"), None


def wikisource(name: str, starts: str) -> Callable[[], tuple[str, None]]:
    """A verse (up to its closing double danda / end of poem) from a Wikisource page."""

    def get() -> tuple[str, None]:
        poem = re.search(r"<poem>(.*?)</poem>", _read(name), re.S).group(1)
        i = poem.index(starts)
        j = poem.find("।।", i)
        verse = poem[i : j if j > 0 else len(poem)]
        return _clean_iast(deva_to_iast(_clean_deva(verse))), None

    return get


@dataclass(frozen=True)
class Spec:
    slug: str
    title: str
    source_id: str | None
    source_ref: str
    extract: Callable[[], tuple[str, str | None]] | None
    review_notes: str = ""


SPECS = [
    Spec("gayatri", "Gāyatrī Mantra", "gretil-rigveda-aufrecht", "RV 3.62.10",
         rv("rv_3,62.10"),
         "Ṛgveda text only. The common recitation prefix 'oṃ bhūr bhuvaḥ svaḥ' "
         "(vyāhṛtis) is not part of RV 3.62.10; advisor to decide whether to include it."),
    Spec("mahamrityunjaya", "Mahāmṛtyuñjaya Mantra", "gretil-rigveda-aufrecht", "RV 7.59.12",
         rv("rv_7,59.12")),
    Spec("asato-ma", "Asato mā sad gamaya", "gretil-brhadaranyaka", "BṛU 1.3.28",
         bru_asato,
         "Source quotes the last line with the particle iti fused ('gamayeti'); the seed "
         "restores 'gamaya'. Commas in the source removed."),
    Spec("saha-navavatu", "Oṃ saha nāvavatu", "gretil-taittiriya",
         "Taittirīya Upaniṣad, śānti-pāṭha (opening of the Bhṛguvallī in this edition)",
         gretil_lines("taittiriya.txt", "oṃ / saha nāv avatu"),
         "CLAUDE.md lists this as TaitU 2.2.2; GRETIL places it as the śānti-pāṭha "
         "opening the Bhṛguvallī. Advisor to confirm the reference."),
    Spec("purnamadah", "Pūrṇamadaḥ", "gretil-isa",
         "Īśa Upaniṣad (Kāṇva), śānti-pāṭha (= BṛU 5.1.1)",
         gretil_lines("isa.txt", "oṃ pūrṇam adaḥ", 2)),
    Spec("bg-2-47", "Bhagavad Gītā 2.47", "gretil-bhagavadgita", "BhG 2.47", bhg("02.047")),
    Spec("sarve-bhavantu", "Sarve bhavantu sukhinaḥ", None, "", None,
         "SOURCE PENDING: no open-corpus source found for the standard verse "
         "('sarve bhavantu sukhinaḥ sarve santu nirāmayāḥ / sarve bhadrāṇi paśyantu "
         "mā kaścid duḥkhabhāg bhavet'). Not seeded until a source is recorded."),
    Spec("guru-brahma", "Guru Brahmā", "wikisource-pratahsmaranam", "प्रातःस्मरणम्, verse 6",
         wikisource("ws_pratahsmaranam.wiki", "गुरुर्ब्रह्मा"),
         "Wikisource reads 'śrīguravai'; the standard reading is 'śrīgurave'. Also "
         "'parabrahma' (one word). Advisor to confirm."),
    Spec("vakratunda", "Vakratuṇḍa mahākāya", "wikisource-pratahsmaranam",
         "प्रातःस्मरणम्, verse 1", wikisource("ws_pratahsmaranam.wiki", "वक्रतुण्ड"),
         "Wikisource reads 'kurū'; the standard reading is 'kuru'. Advisor to confirm."),
    Spec("karagre", "Karāgre vasate", "wikisource-karadarsanam", "करदर्शनम्",
         wikisource("ws_karadarsanam.wiki", "कराग्रे"),
         "Wikisource writes anusvāra in 'goviṃdaḥ' (= govindaḥ, same pronunciation). "
         "Advisor to choose the display spelling."),
]  # fmt: skip


def build(spec: Spec, tk: Toolkit) -> dict:
    doc: dict = {
        "slug": spec.slug,
        "title": spec.title,
        "source_id": spec.source_id,
        "source_ref": spec.source_ref,
        "verified": False,
        "review_notes": spec.review_notes or None,
    }
    if spec.extract is None:
        return doc | {"status": "source_pending"}
    iast, padapatha = spec.extract()
    words = iast.split()
    drafts = tk.draft_line(iast, padapatha=padapatha)
    analyses = []
    for d in drafts:
        cand = d.candidates[d.proposed] if d.proposed is not None else None
        analyses.append(
            {
                "word_position": d.word_index,
                "pada_iast": d.pada,
                "lemma": cand.lemma if cand else None,
                "morphology": {
                    "split_source": d.split_source,
                    "members": d.members,
                    "status": d.status,
                    "proposed": d.to_dict()["candidates"][d.proposed] if cand else None,
                    "candidates": d.to_dict()["candidates"],
                },
            }
        )
    return doc | {
        "status": "draft",
        "iast": iast,
        "devanagari": iast_to_deva(iast),
        "analysis_tool": TOOL,
        "analysis_tool_version": TOOL_VERSION,
        "words": [
            {"position": i, "surface_iast": w, "surface_devanagari": iast_to_deva(w)}
            for i, w in enumerate(words)
        ],
        "analyses": analyses,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tk = Toolkit(VENDOR / "vidyut-0.4.0")
    for spec in SPECS:
        doc = build(spec, tk)
        path = out / f"{spec.slug}.yaml"
        header = (
            "# Generated by `uv run python -m vv_content.seed_build` - initial seed only.\n"
            "# verified: false until an advisor reviews it. Do not hand-edit grammar here;\n"
            "# after seeding, edit in the admin console (the DB is the source of truth).\n"
        )
        path.write_text(
            header + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100), "utf-8"
        )
        print(f"{spec.slug:16} {doc['status']:15} {doc.get('iast', '')[:70]}")


if __name__ == "__main__":
    main()
