"""Accuracy metrics for the scoring spike.

A word is "needs work" in the ground truth when its label is not "ok", and
predicted "needs work" when its score is below the pass threshold.
False alarms matter most: telling a learner a correct word is wrong erodes trust.
"""

from collections import defaultdict
from dataclasses import asdict, dataclass

from scipy.stats import spearmanr


@dataclass
class Metrics:
    words: int
    precision: float
    recall: float
    f1: float
    false_alarm_rate: float  # flagged / truly-correct words
    issue_code_accuracy: float  # among correctly flagged words, right issue code
    recall_by_error: dict[str, float]
    neutral_mean_overall: float  # mean overall score on fully-correct attempts
    neutral_min_overall: int
    spearman_vs_rating: float | None
    mean_latency_s: float

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def compute(rows: list[dict], threshold: int) -> Metrics:
    """rows: one per attempt with keys labels, scores, codes, overall, rating, latency_s."""
    tp = fp = fn = tn = code_ok = 0
    by_err: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # code -> [caught, total]
    neutral, rated = [], []
    for r in rows:
        if all(v == "ok" for v in r["labels"].values()):
            neutral.append(r["overall"])
        if r.get("rating") is not None:
            rated.append((r["overall"], r["rating"]))
        for pos, truth in r["labels"].items():
            pred_bad = r["scores"][pos] < threshold
            if truth == "ok":
                fp += pred_bad
                tn += not pred_bad
            else:
                by_err[truth][1] += 1
                if pred_bad:
                    tp += 1
                    by_err[truth][0] += 1
                    code_ok += r["codes"][pos] == truth
                else:
                    fn += 1
    precision, recall = _safe_div(tp, tp + fp), _safe_div(tp, tp + fn)
    rho = None
    if len(rated) >= 3:
        rho = float(spearmanr([a for a, _ in rated], [b for _, b in rated]).statistic)
    return Metrics(
        words=tp + fp + fn + tn,
        precision=round(precision, 3),
        recall=round(recall, 3),
        f1=round(_safe_div(2 * precision * recall, precision + recall), 3),
        false_alarm_rate=round(_safe_div(fp, fp + tn), 3),
        issue_code_accuracy=round(_safe_div(code_ok, tp), 3),
        recall_by_error={k: round(_safe_div(c, t), 3) for k, (c, t) in sorted(by_err.items())},
        neutral_mean_overall=round(sum(neutral) / len(neutral), 1) if neutral else 0.0,
        neutral_min_overall=min(neutral) if neutral else 0,
        spearman_vs_rating=None if rho is None else round(rho, 3),
        mean_latency_s=round(sum(r["latency_s"] for r in rows) / len(rows), 3) if rows else 0.0,
    )
