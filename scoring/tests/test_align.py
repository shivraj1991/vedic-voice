import numpy as np

from vv_scoring.align import Slot, build_graph, forward, viterbi

from .conftest import VOCAB, synth

BLANK = VOCAB["<pad>"]


def slot(*tokens: str) -> Slot:
    return Slot((tuple((VOCAB[t],) for t in tokens),))


def test_viterbi_spans_follow_token_order():
    post = synth(["t", "ə", "t"])
    ali = viterbi(post.log_probs, build_graph([slot("t"), slot("ə"), slot("t")], BLANK))
    starts = [s for s, _ in ali.slot_spans]
    assert starts == sorted(starts)
    assert starts[0] == 5  # after 5 lead-in blank frames
    assert all(e > s for s, e in ali.slot_spans)


def test_forward_is_at_least_viterbi():
    post = synth(["t", "ə", "t"])
    g = build_graph([slot("t"), slot("ə"), slot("t")], BLANK)
    assert forward(post.log_probs, g) >= viterbi(post.log_probs, g).log_likelihood - 1e-9


def test_alternative_realisations_pick_best_fit():
    # "dh" may be one token (dʰ) or two (d h); audio says "d h".
    dh = Slot((((VOCAB["dʰ"],),), ((VOCAB["d"],), (VOCAB["h"],))))
    post = synth(["d", "h", "ə"])
    g = build_graph([dh, slot("ə")], BLANK)
    single_only = build_graph([slot("dʰ"), slot("ə")], BLANK)
    assert forward(post.log_probs, g) > forward(post.log_probs, single_only) + 5


def test_deletion_slot_is_skippable():
    post = synth(["t", "t"])  # the ə was never said
    with_vowel = build_graph([slot("t"), slot("ə"), slot("t")], BLANK)
    deleted = build_graph([slot("t"), Slot(((),)), slot("t")], BLANK)
    assert forward(post.log_probs, deleted) > forward(post.log_probs, with_vowel)


def test_filler_absorbs_extra_leading_speech():
    post = synth(["s", "u", "s", "u", "t", "ə", "t"])
    slots = [slot("t"), slot("ə"), slot("t")]
    filler = np.array([i for t, i in VOCAB.items() if not t.startswith("<")])
    ali = viterbi(post.log_probs, build_graph(slots, BLANK, filler_ids=filler, filler_penalty=1.0))
    # the first "t" slot starts at the real "t", not at the leading "s u s u"
    assert ali.slot_spans[0][0] >= 5 + 4 * 6
