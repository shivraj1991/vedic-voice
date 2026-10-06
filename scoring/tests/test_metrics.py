from spike.metrics import compute


def row(labels, scores, codes=None, overall=90, rating=None):
    return {
        "labels": labels,
        "scores": scores,
        "codes": codes or {k: None for k in scores},
        "overall": overall,
        "rating": rating,
        "latency_s": 0.1,
    }


def test_counts_hits_misses_and_false_alarms():
    rows = [
        row({0: "ok", 1: "too_short"}, {0: 90, 1: 40}, {0: None, 1: "too_short"}),  # TN, TP
        row({0: "ok", 1: "skipped"}, {0: 50, 1: 80}, {0: "minor", 1: None}),  # FP, FN
        row({0: "ok", 1: "ok"}, {0: 100, 1: 100}, overall=100),  # neutral
    ]
    m = compute(rows, threshold=75)
    assert (m.precision, m.recall, m.f1) == (0.5, 0.5, 0.5)
    assert m.false_alarm_rate == round(1 / 4, 3)
    assert m.issue_code_accuracy == 1.0
    assert m.recall_by_error == {"skipped": 0.0, "too_short": 1.0}
    assert m.neutral_min_overall == 100


def test_spearman_needs_three_rated_attempts():
    rows = [row({0: "ok"}, {0: 90}, overall=o, rating=r) for o, r in [(90, 9), (60, 5), (30, 2)]]
    assert compute(rows, 75).spearman_vs_rating == 1.0
    assert compute(rows[:2], 75).spearman_vs_rating is None
