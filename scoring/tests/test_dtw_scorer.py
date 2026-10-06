"""Behavioural tests for the DTW scorer on synthetic audio with known truth."""

import pytest

from vv_scoring import perturb
from vv_scoring.scorers.base import PASS_THRESHOLD
from vv_scoring.scorers.dtw import DtwScorer
from vv_scoring.synth import Speaker, synthesize
from vv_scoring.types import WordMark

scorer = DtwScorer()


def flagged(result):
    return {w.position: w.issue_code for w in result.words if w.score < PASS_THRESHOLD}


def test_reference_against_itself_is_perfect(reference, words):
    y, marks = reference
    r = scorer.score(y, marks, y, words)
    assert r.overall == 100
    assert flagged(r) == {}


def test_correct_chant_by_another_voice_is_not_flagged(reference, other_speaker, words):
    y, marks = reference
    r = scorer.score(y, marks, other_speaker[0], words)
    assert flagged(r) == {}
    assert r.overall >= 90


@pytest.mark.parametrize(
    "change", [("tempo", 0.8), ("tempo", 1.25), ("pitch", 3), ("pitch", -3), ("noise", 15)]
)
def test_neutral_changes_are_not_flagged(reference, words, change):
    y, marks = reference
    fn, arg = change
    att, _, _ = getattr(perturb, fn)(y, marks, arg)
    assert flagged(scorer.score(y, marks, att, words)) == {}


def test_skipped_word_is_flagged(reference, words):
    y, marks = reference
    att, _, _ = perturb.delete_word(y, marks, 5)  # savitur
    assert flagged(scorer.score(y, marks, att, words)) == {5: "skipped"}


def test_rushed_long_vowel_word_is_flagged_with_vowel_advice(reference, words):
    y, marks = reference
    att, _, _ = perturb.shorten_word(y, marks, 9, factor=0.5)  # dhīmahi
    r = scorer.score(y, marks, att, words)
    assert flagged(r) == {9: "too_short"}
    assert "'ī'" in r.words[9].issue_text


def test_wrong_word_is_flagged(reference, words):
    y, marks = reference
    att, _, _ = perturb.substitute_word(y, marks, 8, with_pos=10)  # devasya -> dhiyo
    assert set(flagged(scorer.score(y, marks, att, words))) == {8}


def test_skipped_word_by_another_voice(words):
    ref, marks = synthesize(words, Speaker())
    other = synthesize([w for w in words if w.position != 7], Speaker(f0=150, seed=4))[0]
    assert 7 in flagged(scorer.score(ref, marks, other, words))


def test_marks_must_match_words(reference, words):
    y, marks = reference
    with pytest.raises(ValueError):
        scorer.score(y, marks[:-1], y, words)
    with pytest.raises(ValueError):
        scorer.score(y, list(reversed(marks)), y, words)


def test_word_mark_validates_order():
    with pytest.raises(ValueError):
        WordMark(0, 1.0, 0.5)


def test_high_childlike_voice_is_not_flagged(reference, words):
    """VTLN: a voice with much higher formants than the reference is still correct."""
    y, marks = reference
    child = synthesize(words, Speaker(f0=260, formant_scale=1.25, tempo=1.1, seed=8))[0]
    r = scorer.score(y, marks, child, words)
    assert flagged(r) == {}
    assert r.details["vtln_warp"] > 1.0
    no_vtln = DtwScorer(vtln_warps=(1.0,)).score(y, marks, child, words)
    assert len(flagged(no_vtln)) > 0  # proves the normalization is what fixes it
