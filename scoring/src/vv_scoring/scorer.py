"""Per-word pronunciation scoring against a reference recitation.

Steps for one recording (`analyse`):
1. Force-align the expected phoneme units to the model posteriors.
2. For every unit, compare the likelihood of the expected sound with curated
   alternatives (ā->a, ṭ->t, deletion, ...) in a local window: the GOP
   (goodness of pronunciation) in nats. Positive = the expected sound fits best.

Scoring a learner (`score`) then compares the learner's GOP per unit with the
reference reciter's GOP for the same unit. The reference acts as calibration:
if the model is unsure about a sound even for the scholar (common for Sanskrit
sounds that are rare in its training languages), the learner is not blamed
for it. Vowel length is additionally checked by duration relative to the
reference, because chanting holds long vowels for two beats.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from . import __version__
from .align import NEG_INF, Slot, build_graph, forward, viterbi
from .model import BLANK, FRAME_SECONDS, Posteriors
from .phonology import LONG_VOWELS, PhonologyError, Word, alternatives, parse_text, realisations

SCORER_VERSION = f"vv-gop-{__version__}"


@dataclass(frozen=True)
class Calibration:
    """Tunable constants; tuned by spike/eval.py. Values are in nats unless noted."""

    gop_cap: float = 4.0  # reference GOP above this counts as "clearly correct"
    deficit_scale: float = 4.0  # unit score = exp(-deficit / scale)
    flag_gop: float = 0.0  # learner GOP must be below this to raise an issue ...
    flag_deficit: float = 2.0  # ... and this much worse than the reference
    # A single dropped sound is weak evidence: CTC models readily skip short vowels
    # even in good recitations, so deletions count less and need a bigger deficit.
    deletion_weight: float = 0.25
    flag_deficit_deletion: float = 6.0
    word_missing_fraction: float = 0.6  # this share of a word's sounds best explained as dropped
    min_weight: float = 0.5  # word score = (1 - w) * mean + w * min of unit scores
    short_vowel_ratio: float = 0.5  # long vowel held < this x reference (tempo-normalised)
    short_vowel_penalty: float = 0.4
    weak_word_score: int = 70  # words below this get a plain-language issue
    filler_penalty: float = 2.5


DEFAULT_CALIBRATION = Calibration()


@dataclass
class UnitAnalysis:
    word: int
    symbol: str
    long: bool
    start: int  # frames
    end: int
    gop: float
    best_alt: str | None  # alternative that came closest ("" = deletion)
    best_alt_issue: tuple[str, str] | None


@dataclass
class RecordingAnalysis:
    """Alignment + GOP of one recording. Cacheable for reference audio."""

    words: list[str]
    units: list[UnitAnalysis]
    n_frames: int
    forced_ll: float
    free_ll: float
    filler_frames: int

    @property
    def tempo(self) -> float:
        d = [u.end - u.start for u in self.units if u.end > u.start]
        return float(np.median(d)) if d else 1.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WordScore:
    index: int
    text: str
    score: int
    start_ms: int
    end_ms: int
    issue_code: str | None = None
    issue_text: str | None = None
    units: list[dict] = field(default_factory=list)


@dataclass
class ScoreResult:
    overall: int
    match_confidence: float
    words: list[WordScore]
    scorer_version: str = SCORER_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def _slots(words: list[Word], vocab: dict[str, int]) -> tuple[list[Slot], list[tuple[int, int]]]:
    slots, index = [], []
    for wi, w in enumerate(words):
        for ui, u in enumerate(w.units):
            slots.append(Slot(realisations(u.symbol, vocab)))
            index.append((wi, ui))
    return slots, index


def analyse(
    post: Posteriors, text: str | list[Word], cal: Calibration = DEFAULT_CALIBRATION
) -> RecordingAnalysis:
    """Align `text` (IAST, words separated by spaces) to a recording and compute GOP."""
    words = parse_text(text) if isinstance(text, str) else text
    vocab, lp = post.vocab, post.log_probs
    blank = vocab[BLANK]
    slots, index = _slots(words, vocab)
    special = {vocab.get(t) for t in ("<pad>", "<s>", "</s>", "<unk>")}
    filler = np.array([i for i in range(lp.shape[1]) if i not in special], dtype=np.int64)

    g = build_graph(slots, blank, filler_ids=filler, filler_penalty=cal.filler_penalty)
    ali = viterbi(lp, g)
    filler_nodes = [i for i, ids in enumerate(g.token_sets) if ids.size == filler.size]
    filler_frames = int(np.isin(ali.node_path, filler_nodes).sum())

    units: list[UnitAnalysis] = []
    spans = ali.slot_spans
    for k, (wi, ui) in enumerate(index):
        unit = words[wi].units[ui]
        lo_k, hi_k = max(k - 1, 0), min(k + 1, len(slots) - 1)
        f0, f1 = spans[lo_k][0], spans[hi_k][1]
        window = lp[f0 : max(f1, f0 + 1)]
        local = slots[lo_k : hi_k + 1]
        pos = k - lo_k
        canon = forward(window, build_graph(local, blank))
        best_ll, best_alt, best_issue = NEG_INF, None, None
        for alt, issue in alternatives(unit.symbol).items():
            try:
                alt_slot = Slot(((),)) if alt is None else Slot(realisations(alt, vocab))
            except PhonologyError:  # alternative not expressible in this model's vocabulary
                continue
            alt_slots = local[:pos] + [alt_slot] + local[pos + 1 :]
            if not any(r for s in alt_slots for r in s.realisations):
                continue
            ll = forward(window, build_graph(alt_slots, blank))
            if ll > best_ll:
                best_ll, best_alt, best_issue = ll, ("" if alt is None else alt), issue
        if canon <= NEG_INF / 2:
            gop = -10.0
        elif best_ll <= NEG_INF / 2:
            gop = 10.0
        else:
            gop = float(np.clip(canon - best_ll, -10.0, 10.0))
        s0, s1 = spans[k]
        units.append(UnitAnalysis(wi, unit.symbol, unit.long, s0, s1, gop, best_alt, best_issue))

    return RecordingAnalysis(
        words=[w.text for w in words],
        units=units,
        n_frames=post.n_frames,
        forced_ll=ali.log_likelihood,
        free_ll=float(lp.max(axis=1).sum()),
        filler_frames=filler_frames,
    )


def _ms(frames: int) -> int:
    return int(round(frames * FRAME_SECONDS * 1000))


def score(
    learner: RecordingAnalysis,
    reference: RecordingAnalysis | None = None,
    cal: Calibration = DEFAULT_CALIBRATION,
) -> ScoreResult:
    """Score a learner analysis, calibrated by the reference analysis of the same text."""
    if reference is not None and [u.symbol for u in reference.units] != [
        u.symbol for u in learner.units
    ]:
        raise ValueError("reference and learner analyses are for different texts")
    tempo_l = learner.tempo
    tempo_r = reference.tempo if reference else None

    per_word: dict[int, list[tuple[float, UnitAnalysis, tuple[str, str] | None, str]]] = {}
    dropped: set[int] = set()  # units best explained as skipped, clearly worse than the reference
    for k, u in enumerate(learner.units):
        ref_u = reference.units[k] if reference else None
        target = min(ref_u.gop, cal.gop_cap) if ref_u else cal.gop_cap
        is_deletion = u.best_alt == ""
        raw_deficit = max(0.0, target - u.gop)
        deficit = raw_deficit * (cal.deletion_weight if is_deletion else 1.0)
        s = float(np.exp(-deficit / cal.deficit_scale))
        issue, heard = None, u.best_alt or ""
        needed = cal.flag_deficit_deletion if is_deletion else cal.flag_deficit
        if u.gop < cal.flag_gop and raw_deficit > needed:
            issue = u.best_alt_issue
        if is_deletion and u.gop < cal.flag_gop and raw_deficit > cal.flag_deficit:
            dropped.add(k)
        if ref_u and tempo_r and u.symbol in LONG_VOWELS and issue is None:
            dur_l = (u.end - u.start) / tempo_l
            dur_r = (ref_u.end - ref_u.start) / tempo_r
            if dur_r > 0 and dur_l / dur_r < cal.short_vowel_ratio:
                s *= cal.short_vowel_penalty
                short = {"ā": "a", "ī": "i", "ū": "u"}.get(u.symbol, u.symbol)
                issue = (
                    "vowel_length_short",
                    'hold the long "{exp}" for two beats; it sounded short like "{heard}"',
                )
                heard = short
        per_word.setdefault(u.word, []).append((s, u, issue, heard))

    dropped_ids = {id(learner.units[k]) for k in dropped}
    words: list[WordScore] = []
    for wi, text in enumerate(learner.words):
        items = per_word.get(wi, [])
        if not items:
            continue
        unit_scores = np.array([s for s, *_ in items])
        w = cal.min_weight
        wscore = int(round(100 * ((1 - w) * unit_scores.mean() + w * unit_scores.min())))
        start, end = items[0][1].start, items[-1][1].end
        ws = WordScore(wi, text, wscore, _ms(start), _ms(end))
        ws.units = [
            {"symbol": u.symbol, "score": round(s, 3), "gop": round(u.gop, 2), "issue": i and i[0]}
            for s, u, i, _ in items
        ]
        flagged = [(s, u, i, h) for s, u, i, h in items if i]
        missing = [x for x in items if id(x[1]) in dropped_ids]
        if len(missing) >= max(2, int(np.ceil(cal.word_missing_fraction * len(items)))):
            ws.issue_code, ws.issue_text = "word_missing", f'We could not hear "{text}" clearly.'
        elif flagged and wscore < cal.weak_word_score:
            s, u, (code, tmpl), heard = min(flagged, key=lambda x: x[0])
            ws.issue_code = code
            ws.issue_text = f'In "{text}": ' + tmpl.format(exp=u.symbol, heard=heard, word=text)
        elif wscore < cal.weak_word_score:
            worst = min(items, key=lambda x: x[0])[1]
            ws.issue_code = "unclear"
            ws.issue_text = f'In "{text}": the "{worst.symbol}" sound was unclear.'
        words.append(ws)

    # Match: how far the forced path is from the unconstrained best path, per frame.
    gap = max(0.0, (learner.free_ll - learner.forced_ll) / max(learner.n_frames, 1))
    match = float(np.exp(-gap))
    overall = int(round(np.mean([w.score for w in words]))) if words else 0
    return ScoreResult(overall=overall, match_confidence=round(match, 3), words=words)
