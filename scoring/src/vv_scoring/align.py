"""CTC alignment over a small phoneme graph.

Why a graph instead of a plain label sequence: one Sanskrit sound can be
realised as different token sequences by the acoustic model (aspirated "dh" is
either the single token "dʰ" or "d" followed by "h"; visarga may carry an echo
vowel). Each sound ("slot") therefore has several realisations, and the
alignment picks whichever fits the audio. The same machinery computes
goodness-of-pronunciation by comparing the likelihood of the expected slot
against curated alternatives (ā -> a, ṭ -> t, deletion, ...).

Optional filler nodes at the start and end absorb speech that is not part of
the text (an "oṃ" before the shloka, the next line read by mistake), so it is
not forced into the first or last word.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

NEG_INF = -1e30

Realisation = tuple[tuple[int, ...], ...]  # sequence of token-id sets; () = skip the slot


@dataclass(frozen=True)
class Slot:
    """One expected sound: its acceptable realisations (each a sequence of token sets)."""

    realisations: tuple[Realisation, ...]


@dataclass
class Graph:
    token_sets: list[np.ndarray] = field(default_factory=list)
    penalty: list[float] = field(default_factory=list)
    preds: list[list[int]] = field(default_factory=list)
    slot_of: list[int] = field(default_factory=list)  # -1 for blanks outside slots / filler
    is_label: list[bool] = field(default_factory=list)
    start: list[int] = field(default_factory=list)
    final: list[int] = field(default_factory=list)

    def add(self, ids, slot: int, is_label: bool, preds: list[int], penalty: float = 0.0) -> int:
        self.token_sets.append(np.asarray(ids, dtype=np.int64))
        self.penalty.append(penalty)
        self.preds.append(list(preds))
        self.slot_of.append(slot)
        self.is_label.append(is_label)
        return len(self.token_sets) - 1


def build_graph(
    slots: list[Slot], blank: int, filler_ids: np.ndarray | None = None, filler_penalty: float = 2.5
) -> Graph:
    """Linear CTC graph over slots, with alternative realisations per slot."""
    g = Graph()
    b0 = g.add([blank], -1, False, [])
    frontier: list[tuple[int, frozenset[int] | None]] = [(b0, None)]
    g.start = [b0]
    if filler_ids is not None:
        f0 = g.add(filler_ids, -1, False, [b0], -filler_penalty)
        g.preds[b0].append(f0)
        g.start.append(f0)
        frontier.append((f0, frozenset(filler_ids.tolist())))

    for k, slot in enumerate(slots):
        new_frontier: list[tuple[int, frozenset[int] | None]] = []
        for real in slot.realisations:
            if not real:  # deletion: next slot connects straight to this slot's predecessors
                new_frontier.extend(frontier)
                continue
            exits = frontier
            for ids in real:
                ids_set = frozenset(ids)
                # CTC: identical consecutive labels must be separated by a blank.
                preds = [n for n, s in exits if s is None or s.isdisjoint(ids_set)]
                lab = g.add(sorted(ids_set), k, True, preds)
                blk = g.add([blank], k, False, [lab])
                exits = [(lab, ids_set), (blk, None)]
            new_frontier.extend(exits)
        # de-duplicate while preserving order
        seen: set[int] = set()
        frontier = [(n, s) for n, s in new_frontier if not (n in seen or seen.add(n))]

    g.final = [n for n, _ in frontier]
    if filler_ids is not None:
        f1 = g.add(filler_ids, -1, False, [n for n, _ in frontier], -filler_penalty)
        b1 = g.add([blank], -1, False, [f1])
        g.preds[f1].append(b1)
        g.final += [f1, b1]
    return g


def _emissions(log_probs: np.ndarray, g: Graph) -> np.ndarray:
    """E[t, n] = log sum_{tok in set(n)} p(tok | frame t) + penalty(n)."""
    cache: dict[tuple[int, ...], np.ndarray] = {}
    cols = []
    for ids, pen in zip(g.token_sets, g.penalty, strict=True):
        key = tuple(ids.tolist())
        if key not in cache:
            sub = log_probs[:, ids]
            m = sub.max(axis=1, keepdims=True)
            cache[key] = (m + np.log(np.exp(sub - m).sum(axis=1, keepdims=True)))[:, 0]
        cols.append(cache[key] + pen)
    return np.stack(cols, axis=1)


def _pred_matrix(g: Graph) -> np.ndarray:
    """Padded predecessor matrix incl. self-loop; pad index = N (a -inf sentinel)."""
    n = len(g.preds)
    width = 1 + max((len(p) for p in g.preds), default=0)
    mat = np.full((n, width), n, dtype=np.int64)
    for i, p in enumerate(g.preds):
        mat[i, 0] = i
        mat[i, 1 : 1 + len(p)] = p
    return mat


@dataclass(frozen=True)
class Alignment:
    log_likelihood: float  # Viterbi path score
    node_path: np.ndarray  # (T,) node index per frame
    slot_path: np.ndarray  # (T,) slot index per frame (-1 outside slots)
    label_frames: np.ndarray  # (T,) bool: frame sits on a label (non-blank) node
    slot_spans: list[
        tuple[int, int]
    ]  # per slot: [first label frame, next slot's first label frame)


def viterbi(log_probs: np.ndarray, g: Graph) -> Alignment:
    t_len, n = log_probs.shape[0], len(g.preds)
    if t_len == 0:
        raise ValueError("empty posteriors")
    emis = _emissions(log_probs, g)
    pm = _pred_matrix(g)
    dp = np.full(n + 1, NEG_INF)
    dp[g.start] = emis[0, g.start]
    back = np.zeros((t_len, n), dtype=np.int32)
    back[0] = np.arange(n)
    for t in range(1, t_len):
        cand = dp[pm]
        arg = cand.argmax(axis=1)
        best = cand[np.arange(n), arg]
        back[t] = pm[np.arange(n), arg]
        dp[:n] = best + emis[t]
    final = np.asarray(g.final)
    end = int(final[dp[final].argmax()])
    score = float(dp[end])
    path = np.empty(t_len, dtype=np.int64)
    path[-1] = end
    for t in range(t_len - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    slot_of = np.asarray(g.slot_of)
    is_label = np.asarray(g.is_label)
    slot_path = slot_of[path]
    label_frames = is_label[path]
    n_slots = int(slot_of.max()) + 1 if slot_of.size else 0
    starts = np.full(n_slots, -1)
    for t in range(t_len):
        s = slot_path[t]
        if s >= 0 and label_frames[t] and starts[s] < 0:
            starts[s] = t
    # Deleted slots (no label frame) get a zero-length span at the next slot's start.
    for s in range(n_slots - 1, -1, -1):
        if starts[s] < 0:
            starts[s] = starts[s + 1] if s + 1 < n_slots else _last_label_end(slot_path, t_len)
    spans = []
    for s in range(n_slots):
        end_f = starts[s + 1] if s + 1 < n_slots else _last_label_end(slot_path, t_len, s)
        spans.append((int(starts[s]), int(max(end_f, starts[s]))))
    return Alignment(score, path, slot_path, label_frames, spans)


def _last_label_end(slot_path: np.ndarray, t_len: int, slot: int | None = None) -> int:
    """End of the final slot: last frame that still belongs to it, plus one."""
    idx = np.nonzero(slot_path == slot)[0] if slot is not None else np.nonzero(slot_path >= 0)[0]
    return int(idx[-1]) + 1 if idx.size else t_len


def forward(log_probs: np.ndarray, g: Graph) -> float:
    """Total log-likelihood over all paths (CTC forward algorithm on the graph)."""
    t_len, n = log_probs.shape[0], len(g.preds)
    emis = _emissions(log_probs, g)
    pm = _pred_matrix(g)
    a = np.full(n + 1, NEG_INF)
    a[g.start] = emis[0, g.start]
    for t in range(1, t_len):
        cand = a[pm]
        m = cand.max(axis=1)
        safe = np.where(m > NEG_INF / 2, m, 0.0)
        with np.errstate(divide="ignore"):
            s = safe + np.log(np.exp(cand - safe[:, None]).sum(axis=1))
        a[:n] = np.where(m > NEG_INF / 2, s, NEG_INF) + emis[t]
    fin = a[np.asarray(g.final)]
    m = fin.max()
    if m <= NEG_INF / 2:
        return NEG_INF
    return float(m + np.log(np.exp(fin - m).sum()))
