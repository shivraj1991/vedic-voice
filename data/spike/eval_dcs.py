"""Milestone 0b: measure Vidyut against Digital Corpus of Sanskrit (DCS) gold analyses.

Questions the content pipeline depends on:
1. Split: how often does the segmenter split a sentence into the same padas as
   the DCS annotators?
2. Coverage: for how many gold padas does the lexicon know the form at all?
3. Candidate recall: is the gold case + number (nouns) among the lexicon's
   candidates? (The advisor picks from candidates, so this bounds how often they
   can just click instead of typing an analysis.)
4. Top-1: is the gold reading the default we propose?

DCS tags look like `śāstre_N_LNeS_14`: POS N, case L(ocative), gender Ne(uter),
number S(ingular). Groups split by sandhi appear as `surface____1-3` followed by
their parts. Compound members carry no case (`mārga_N__6`).

    uv run python -m spike.eval_dcs --sentences 2000
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

from vv_content.analysis import Toolkit

ROOT = Path(__file__).resolve().parents[1]
CASE = {"N": "nominative", "A": "accusative", "I": "instrumental", "D": "dative",
        "B": "ablative", "G": "genitive", "L": "locative", "V": "vocative"}  # fmt: skip
NUMBER = {"S": "singular", "Z": "dual", "D": "dual", "P": "plural"}
NOMINAL = {"N", "A", "P", "M"}  # noun, adjective, pronoun, numeral
TAG = re.compile(r"^(?P<form>.+?)_(?P<pos>[A-Z]+)_(?P<feats>[A-Za-z]*)_(?P<idx>[\d-]+)$")


def parse_gold(morph: str) -> list[dict]:
    """Leaf tokens of a DCS sentence, with compound members merged into their head."""
    leaves = []
    for tok in morph.split():
        if "____" in tok:  # sandhi group header; its parts follow
            continue
        m = TAG.match(tok)
        if not m:
            continue
        leaves.append(m.groupdict())
    words: list[dict] = []
    prefix = ""
    for leaf in leaves:
        is_member = leaf["pos"] in NOMINAL and leaf["feats"] in ("", "Ma", "Fe", "Ne")
        if is_member:
            prefix += leaf["form"]
            continue
        words.append({**leaf, "form": prefix + leaf["form"], "compound": bool(prefix)})
        prefix = ""
    if prefix:
        words.append({"form": prefix, "pos": "N", "feats": "", "idx": "", "compound": True})
    return words


def norm(form: str) -> str:
    """Compare padas up to final-sound variation (pausa ḥ vs s/r, ṃ vs m)."""
    form = form.strip("'").lower()
    form = re.sub(r"[ḥsr]$", "ḥ", form)
    return re.sub(r"[ṃm]$", "m", form)


def f1(gold: list[str], pred: list[str]) -> float:
    g, p = Counter(gold), Counter(pred)
    tp = sum((g & p).values())
    if not tp:
        return 0.0
    prec, rec = tp / sum(p.values()), tp / sum(g.values())
    return 2 * prec * rec / (prec + rec)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dcs", default=str(ROOT / "vendor" / "dcs_morphology.csv"))
    ap.add_argument("--vidyut", default=str(ROOT / "vendor" / "vidyut-0.4.0"))
    ap.add_argument("--sentences", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(ROOT / "spike" / "out"))
    args = ap.parse_args()

    csv.field_size_limit(sys.maxsize)
    with open(args.dcs, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rng = random.Random(args.seed)
    rng.shuffle(rows)
    tk = Toolkit(args.vidyut)

    n = exact = exact_c = skipped = 0
    f1s: list[float] = []
    f1s_c: list[float] = []
    cov = recall = top1 = nominal = gold_words = 0
    examples: list[dict] = []
    for row in rows:
        if n >= args.sentences:
            break
        sent = row["sentence"].strip()
        gold = parse_gold(row["morphology"])
        if not gold or not (3 <= len(sent.split()) <= 16) or "'" in sent:
            continue
        # Some rows in this mirror lack annotations for the last words; skip any
        # sentence whose gold padas do not cover (almost) all of its letters.
        letters = len(re.sub(r"\W", "", sent))
        if sum(len(w["form"]) for w in gold) < 0.9 * letters:
            skipped += 1
            continue
        n += 1
        g_forms = [norm(w["form"]) for w in gold]
        p_forms = [norm(p) for p in tk.split(sent, conservative=False) for p in [p[1]]]
        c_forms = [norm(p) for p in tk.split(sent, conservative=True) for p in [p[1]]]
        exact += g_forms == p_forms
        exact_c += g_forms == c_forms
        f1s.append(f1(g_forms, p_forms))
        f1s_c.append(f1(g_forms, c_forms))
        if len(examples) < 25 and g_forms != c_forms:
            examples.append({"sentence": sent, "gold": g_forms, "vidyut": c_forms})

        for w in gold:
            gold_words += 1
            cands = tk.lookup(w["form"])
            cov += bool(cands)
            feats = w["feats"]
            if w["pos"] in NOMINAL and len(feats) >= 4 and not w["compound"]:
                case, number = CASE.get(feats[0]), NUMBER.get(feats[-1])
                if not case or not number:
                    continue
                nominal += 1
                hits = [(c.case, c.number) == (case, number) for c in cands]
                recall += any(hits)
                top1 += bool(hits and hits[0])

    result = {
        "sentences": n,
        "skipped_incomplete_gold": skipped,
        "split_exact_match": round(exact / n, 3),
        "split_token_f1": round(sum(f1s) / n, 3),
        "split_exact_match_conservative": round(exact_c / n, 3),
        "split_token_f1_conservative": round(sum(f1s_c) / n, 3),
        "lexicon_coverage": round(cov / gold_words, 3),
        "nominal_case_number_in_candidates": round(recall / nominal, 3),
        "nominal_case_number_top1": round(top1 / nominal, 3),
        "gold_words": gold_words,
        "gold_nominals": nominal,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "dcs_eval.json").write_text(
        json.dumps(result | {"split_errors": examples}, ensure_ascii=False, indent=1), "utf-8"
    )
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
