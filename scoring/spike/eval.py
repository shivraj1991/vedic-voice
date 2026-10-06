"""Milestone 0 evaluation harness for vv_scoring.

There are no advisor labels yet, so ground truth comes from controlled edits
of real recordings (we know exactly which word we broke) plus two sanity
checks on unedited audio:

  clean       learner vs reference, same text (other speakers, unedited)
              -> scores should be high, few words flagged
  wrong_text  learner audio scored against a different text
              -> match_confidence must separate this from `clean`
  deletion    one word cut out of the learner audio -> that word flagged
  substitute  one word replaced by a word from another text -> flagged
  vowel_short a long vowel shortened to ~40% -> that word flagged
  noise       clean learner + white noise at 10 dB SNR -> few extra flags

Outputs (in --out, gitignored): report.json, summary.md, review.html (listen
to every case, click a word to hear it, label words, export labels as JSON),
and audio/*.wav for the page.

    uv run python -m spike.eval --model-dir models/w2v2-xlsr53-espeak --out spike/out
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pickle
import random
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from vv_scoring.audio import SAMPLE_RATE
from vv_scoring.model import FRAME_SECONDS, PhonemeModel, Posteriors
from vv_scoring.phonology import LONG_VOWELS
from vv_scoring.scorer import (
    DEFAULT_CALIBRATION,
    Calibration,
    RecordingAnalysis,
    analyse,
    score,
)

from .corpus import Recording, load_all, wav_bytes
from .review import write_review


class Runner:
    """Model + posterior cache (posteriors are the slow part)."""

    def __init__(self, model_dir: str, onnx_file: str, cache_dir: Path):
        self.model = PhonemeModel(model_dir, onnx_file)
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.model_seconds = 0.0
        self.audio_seconds = 0.0

    def posteriors(self, audio: np.ndarray, key: str) -> Posteriors:
        f = self.cache_dir / f"{key}.npy"
        if f.exists():
            return Posteriors(np.load(f).astype(np.float64), self.model.vocab)
        t0 = time.time()
        post = self.model.posteriors(audio)
        self.model_seconds += time.time() - t0
        self.audio_seconds += audio.size / SAMPLE_RATE
        np.save(f, post.log_probs.astype(np.float16))
        return post


@dataclasses.dataclass
class Case:
    id: str
    kind: str
    group: str
    text: str
    learner_id: str
    reference_id: str
    target_word: int | None
    analysis: RecordingAnalysis
    audio_key: str  # file name under out/audio
    note: str = ""


def _span_samples(an: RecordingAnalysis, word: int) -> tuple[int, int]:
    units = [u for u in an.units if u.word == word]
    hop = int(FRAME_SECONDS * SAMPLE_RATE)
    return units[0].start * hop, units[-1].end * hop


def _choose_reference(recs: list[Recording], analyses: dict[str, RecordingAnalysis]) -> Recording:
    def quality(r: Recording) -> float:
        an = analyses[r.id]
        gap = (an.free_ll - an.forced_ll) / max(an.n_frames, 1)
        return -gap - 0.5 * an.filler_frames / max(an.n_frames, 1)

    return max(recs, key=quality)


def build_cases(runner: Runner, recs: list[Recording], args, rng: random.Random) -> tuple:
    by_group: dict[str, list[Recording]] = defaultdict(list)
    for r in recs:
        by_group[r.group].append(r)
    groups = sorted(by_group, key=lambda g: -len(by_group[g]))[: args.max_groups]
    analyses: dict[str, RecordingAnalysis] = {}
    audio_store: dict[str, np.ndarray] = {}
    for g in groups:
        for r in by_group[g][: args.max_per_group]:
            analyses[r.id] = analyse(runner.posteriors(r.audio, r.sha1), r.text)
            audio_store[r.id] = r.audio
    refs = {g: _choose_reference(by_group[g][: args.max_per_group], analyses) for g in groups}

    cases: list[Case] = []

    def add(kind, g, rec, audio, text, target=None, note="", key=None):
        key = key or f"{kind}-{rec.id}-{len(cases)}"
        if kind == "clean" or kind == "wrong_text":
            an = (
                analyses[rec.id]
                if kind == "clean"
                else analyse(runner.posteriors(audio, rec.sha1), text)
            )
        else:
            import hashlib

            h = hashlib.sha1(audio.tobytes()).hexdigest()
            an = analyse(runner.posteriors(audio, h), text)
        audio_store[key] = audio
        cases.append(Case(key, kind, g, text, rec.id, refs[g].id, target, an, key, note))

    all_words = []  # (rec, word_idx) pool for substitution
    for g in groups:
        for r in by_group[g][: args.max_per_group]:
            for wi in range(len(analyses[r.id].words)):
                all_words.append((r, wi))

    for g in groups:
        ref = refs[g]
        others = [r for r in by_group[g][: args.max_per_group] if r.id != ref.id]
        for r in others:
            an = analyses[r.id]
            add("clean", g, r, r.audio, r.text, key=f"clean-{r.id}")
            # wrong text: score this audio against another group's text
            other_g = rng.choice([x for x in groups if x != g]) if len(groups) > 1 else None
            if other_g:
                add("wrong_text", other_g, r, r.audio, by_group[other_g][0].text,
                    note=f"audio of {g}")  # fmt: skip
            n_words = len(an.words)
            # deletion
            w = rng.randrange(n_words)
            s0, s1 = _span_samples(an, w)
            if s1 - s0 > 0.1 * SAMPLE_RATE:
                audio = np.concatenate([r.audio[:s0], r.audio[s1:]])
                add("deletion", g, r, audio, r.text, w, f'cut "{an.words[w]}"')
            # substitution with a word of similar length from another text
            w = rng.randrange(n_words)
            s0, s1 = _span_samples(an, w)
            pool = [(o, wi) for o, wi in all_words if o.group != g]
            if pool and s1 - s0 > 0.1 * SAMPLE_RATE:
                cand = rng.sample(pool, min(30, len(pool)))

                def dur_gap(item, s0=s0, s1=s1):
                    a0, a1 = _span_samples(analyses[item[0].id], item[1])
                    return abs((a1 - a0) - (s1 - s0))

                o, owi = min(cand, key=dur_gap)
                a0, a1 = _span_samples(analyses[o.id], owi)
                audio = np.concatenate([r.audio[:s0], o.audio[a0:a1], r.audio[s1:]])
                add("substitute", g, r, audio, r.text, w,
                    f'"{an.words[w]}" replaced by "{analyses[o.id].words[owi]}"')  # fmt: skip
            # vowel shortening
            longs = [u for u in an.units if u.symbol in LONG_VOWELS and u.end - u.start >= 6]
            if longs:
                u = rng.choice(longs)
                hop = int(FRAME_SECONDS * SAMPLE_RATE)
                v0, v1 = u.start * hop, u.end * hop
                keep = int(0.2 * (v1 - v0))
                audio = np.concatenate([r.audio[: v0 + keep], r.audio[v1 - keep :]])
                add("vowel_short", g, r, audio, r.text, u.word,
                    f'"{u.symbol}" in "{an.words[u.word]}" shortened to 40%')  # fmt: skip
            # noise
            sig = r.audio
            p = float(np.mean(sig**2)) + 1e-12
            noise = np.random.default_rng(rng.randrange(1 << 30)).normal(
                0, np.sqrt(p / 10 ** (10 / 10)), sig.size
            )
            add(
                "noise",
                g,
                r,
                (sig + noise).astype(np.float32),
                r.text,
                None,
                "white noise 10 dB SNR",
            )
    return cases, analyses, refs, audio_store


def evaluate(cases: list[Case], analyses, refs, cal: Calibration) -> dict:
    rows = []
    for c in cases:
        ref_an = analyses[c.reference_id]
        res = score(c.analysis, ref_an, cal)
        flagged = [w.index for w in res.words if w.issue_code]
        target_flagged = c.target_word in flagged if c.target_word is not None else None
        lowest = min(res.words, key=lambda w: w.score).index if res.words else None
        rows.append(
            {
                "case": c.id, "kind": c.kind, "overall": res.overall,
                "match": res.match_confidence, "n_words": len(res.words),
                "flagged": flagged, "target": c.target_word, "target_flagged": target_flagged,
                "target_lowest": (lowest == c.target_word) if c.target_word is not None else None,
                "false_flags": len([i for i in flagged if i != c.target_word]),
                "result": res.to_dict(),
            }
        )  # fmt: skip
    return {"rows": rows, "metrics": metrics(rows)}


def metrics(rows: list[dict]) -> dict:
    out: dict[str, dict] = {}
    by = defaultdict(list)
    for r in rows:
        by[r["kind"]].append(r)
    for kind, rs in by.items():
        m = {
            "n": len(rs),
            "overall_mean": round(float(np.mean([r["overall"] for r in rs])), 1),
            "match_mean": round(float(np.mean([r["match"] for r in rs])), 3),
            "false_flag_rate": round(
                sum(r["false_flags"] for r in rs)
                / max(1, sum(r["n_words"] - (r["target"] is not None) for r in rs)),
                3,
            ),
        }
        tf = [r["target_flagged"] for r in rs if r["target_flagged"] is not None]
        if tf:
            m["target_recall"] = round(sum(tf) / len(tf), 3)
            m["target_is_lowest"] = round(sum(bool(r["target_lowest"]) for r in rs) / len(tf), 3)
        out[kind] = m
    clean = [r["match"] for r in by.get("clean", [])]
    wrong = [r["match"] for r in by.get("wrong_text", [])]
    if clean and wrong:
        # AUC: probability a clean case has higher match than a wrong-text case
        auc = np.mean([[c > w for w in wrong] for c in clean])
        thr = sorted(clean)[max(0, int(0.05 * len(clean)) - 1)]  # keeps ~95% of clean
        out["match_separation"] = {
            "auc": round(float(auc), 3),
            "threshold_keep_95pct_clean": round(thr, 3),
            "wrong_text_rejected_at_threshold": round(float(np.mean([w < thr for w in wrong])), 3),
        }
    return out


GRID = {
    "flag_deficit": (1.5, 2.0, 3.0),
    "flag_deficit_deletion": (4.0, 6.0, 8.0),
    "deletion_weight": (0.25, 0.5),
    "weak_word_score": (60, 70),
    "min_weight": (0.3, 0.5),
}


def tune(cases, analyses, refs) -> list[dict]:
    """Grid over flagging thresholds.

    Objective = mean target recall (deletion, substitute, vowel_short) minus
    2 x false-flag rate on clean recordings: a wrongly flagged word costs the
    learner's trust more than a missed one.
    """
    import itertools

    grid = []
    keys = list(GRID)
    for values in itertools.product(*GRID.values()):
        params = dict(zip(keys, values, strict=True))
        cal = dataclasses.replace(DEFAULT_CALIBRATION, **params)
        m = evaluate(cases, analyses, refs, cal)["metrics"]
        recall = np.mean(
            [m[k]["target_recall"] for k in ("deletion", "substitute", "vowel_short") if k in m]
        )
        ffr = m["clean"]["false_flag_rate"] if "clean" in m else 0.0
        grid.append(
            params
            | {
                "recall": round(float(recall), 3),
                "false_flag_rate": round(float(ffr), 3),
                "objective": round(float(recall - 2 * ffr), 3),
            }
        )
    return sorted(grid, key=lambda g: -g["objective"])


def write_summary(path: Path, metrics_: dict, grid: list[dict], info: dict) -> None:
    lines = [
        "# Scoring spike summary",
        "",
        f"- scorer: `{info['scorer_version']}`",
        f"- model: `{info['model']}`",
        f"- recordings: {info['n_recordings']} in {info['n_groups']} texts",
        f"- model speed: {info['rtf']} s per audio second",
        "",
        "| case kind | n | overall | match | target recall | target lowest | false-flag rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for kind in ("clean", "noise", "deletion", "substitute", "vowel_short", "wrong_text"):
        if kind in metrics_:
            m = metrics_[kind]
            lines.append(
                f"| {kind} | {m['n']} | {m['overall_mean']} | {m['match_mean']} | "
                f"{m.get('target_recall', '–')} | {m.get('target_is_lowest', '–')} | "
                f"{m['false_flag_rate']} |"
            )
    if "match_separation" in metrics_:
        ms = metrics_["match_separation"]
        rejected = ms["wrong_text_rejected_at_threshold"]
        lines += [
            "",
            f"Match confidence, clean vs wrong text: AUC {ms['auc']}; threshold "
            f"{ms['threshold_keep_95pct_clean']} rejects {rejected:.0%} of wrong-text cases "
            "while keeping 95% of clean ones.",
        ]
    if grid:
        lines += [
            "",
            "Top calibration settings (objective = recall − 2 × false-flag rate):",
            "",
            "| " + " | ".join(GRID) + " | recall | clean false-flag | objective |",
            "|" + "---|" * (len(GRID) + 3),
        ]
        for gr in grid[:5]:
            cells = [str(gr[k]) for k in GRID] + [
                str(gr["recall"]),
                str(gr["false_flag_rate"]),
                str(gr["objective"]),
            ]
            lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines) + "\n", "utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--model-dir", default="models/w2v2-xlsr53-espeak")
    ap.add_argument("--onnx-file", default="model.onnx")
    ap.add_argument("--out", default="spike/out")
    ap.add_argument("--max-groups", type=int, default=40)
    ap.add_argument("--max-per-group", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-tune", action="store_true")
    ap.add_argument("--no-review", action="store_true")
    ap.add_argument(
        "--reuse-cases", action="store_true", help="reload out/cases.pkl (fast re-tuning)"
    )
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    recs = load_all()
    print(f"[eval] {len(recs)} recordings")
    runner = Runner(args.model_dir, args.onnx_file, out / "cache" / Path(args.onnx_file).stem)
    pkl = out / "cases.pkl"
    if args.reuse_cases and pkl.exists():
        cases, analyses, refs, audio_store = pickle.loads(pkl.read_bytes())
    else:
        cases, analyses, refs, audio_store = build_cases(runner, recs, args, rng)
        pkl.write_bytes(pickle.dumps((cases, analyses, refs, audio_store)))
    print(f"[eval] {len(cases)} cases")
    result = evaluate(cases, analyses, refs, DEFAULT_CALIBRATION)
    grid = [] if args.no_tune else tune(cases, analyses, refs)
    from vv_scoring.scorer import SCORER_VERSION

    info = {
        "scorer_version": SCORER_VERSION,
        "model": f"{args.model_dir}/{args.onnx_file}",
        "n_recordings": len(analyses),
        "n_groups": len(refs),
        "rtf": round(runner.model_seconds / max(runner.audio_seconds, 1e-9), 3)
        if runner.audio_seconds
        else "cached",
    }
    report = {"info": info, "metrics": result["metrics"], "tuning": grid, "rows": result["rows"]}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    write_summary(out / "summary.md", result["metrics"], grid, info)
    print((out / "summary.md").read_text("utf-8"))

    if not args.no_review:
        audio_dir = out / "audio"
        audio_dir.mkdir(exist_ok=True)
        rec_by_id = {r.id: r for r in recs}
        for key, audio in audio_store.items():
            (audio_dir / f"{key}.wav").write_bytes(wav_bytes(audio))
        write_review(out / "review.html", cases, result["rows"], refs, analyses, rec_by_id)
        print(f"[eval] review page: {out / 'review.html'}")


if __name__ == "__main__":
    main()
