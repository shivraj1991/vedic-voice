"""Scoring logic on synthetic posteriors (no model download needed)."""

from vv_scoring.scorer import analyse, score

from .conftest import synth

# "tat dhīmahi" said correctly, in tokens of the tiny test vocabulary
GOOD = ["t̪", "ə", "t̪", "dʰ", "iː", "m", "ə", "h", "i"]
TEXT = "tat dhīmahi"


def run(tokens, text=TEXT, ref_tokens=GOOD):
    ref = analyse(synth(ref_tokens), text)
    return score(analyse(synth(tokens), text), ref)


def test_correct_recitation_scores_high_without_issues():
    res = run(GOOD)
    assert res.overall >= 90
    assert all(w.issue_code is None for w in res.words)
    assert res.match_confidence > 0.8
    assert [w.text for w in res.words] == ["tat", "dhīmahi"]
    assert res.words[0].start_ms < res.words[1].start_ms


def test_short_vowel_for_long_is_flagged_on_the_right_word():
    # The reference holds ī for two beats; the learner clips it.
    ref = ["t̪", "ə", "t̪", "dʰ", ("iː", 10), "m", "ə", "h", "i"]
    learner = ["t̪", "ə", "t̪", "dʰ", ("iː", 2), "m", "ə", "h", "i"]
    res = run(learner, ref_tokens=ref)
    tat, dhimahi = res.words
    assert tat.issue_code is None
    assert dhimahi.issue_code == "vowel_length_short"
    assert "ī" in dhimahi.issue_text
    assert dhimahi.score < tat.score


def test_missing_aspiration_is_flagged():
    res = run(["t̪", "ə", "t̪", "d", "iː", "m", "ə", "h", "i"])  # dīmahi
    assert res.words[1].issue_code == "aspiration_missing"


def test_retroflex_said_as_dental_is_flagged():
    text = "vareṇyaṃ"
    ref = ["ʋ", "ə", "ɾ", "e", "ɳ", "j", "ə", "m"]
    res = run(["ʋ", "ə", "ɾ", "e", "n", "j", "ə", "m"], text, ref)
    assert res.words[0].issue_code == "retroflex_missing"


def test_reference_calibrates_sounds_the_model_misses():
    # If the reference reciter also "sounds dental" to the model, don't blame the learner.
    text = "vareṇyaṃ"
    dental = ["ʋ", "ə", "ɾ", "e", "n", "j", "ə", "m"]
    res = run(dental, text, ref_tokens=dental)
    assert res.words[0].issue_code is None


def test_skipped_word_is_flagged():
    res = run(["dʰ", "iː", "m", "ə", "h", "i"])  # "tat" not said
    assert res.words[0].issue_code is not None
    assert res.words[0].score < 70
    assert res.words[1].issue_code is None


def test_wrong_text_has_low_match_confidence():
    good = run(GOOD)
    wrong = run(["s", "u", "b", "ə", "l", "o", "k", "e", "ʃ", "u", "s", "u"])
    assert wrong.match_confidence < good.match_confidence - 0.3
    assert wrong.overall < good.overall
