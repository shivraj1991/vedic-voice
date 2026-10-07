from vv_scoring.translit import deva_to_iast


def test_basic_words():
    assert deva_to_iast("गुरुर्ब्रह्मा गुरुर्विष्णुः") == "gururbrahmā gururviṣṇuḥ"
    assert deva_to_iast("अग्निमीळे पुरोहितं") == "agnimīḷe purohitaṃ"
    assert deva_to_iast("यज्ञस्य") == "yajñasya"


def test_inherent_a_and_virama():
    assert deva_to_iast("तत्") == "tat"
    assert deva_to_iast("कर्म") == "karma"
    assert deva_to_iast("सत्यं") == "satyaṃ"


def test_independent_vowels_om_and_punctuation():
    assert deva_to_iast("ॐ") == "oṃ"
    assert deva_to_iast("ऋतम् ।") == "ṛtam |"
    assert deva_to_iast("औषधम्") == "auṣadham"


def test_accent_marks_dropped():
    assert deva_to_iast("अ॒ग्निमी॑ळे") == "agnimīḷe"
