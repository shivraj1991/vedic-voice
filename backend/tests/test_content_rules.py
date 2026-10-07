"""The non-negotiable content rules, tested against real Postgres."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from vv_backend.content import (
    Actor,
    InvalidEdit,
    PermissionDenied,
    Role,
    get_verified_shloka,
    list_verified_shlokas,
    update_shloka,
    update_word_analysis,
    verify_shloka,
    verify_word_analysis,
)
from vv_backend.db.models import ContentAudit, Shloka, ShlokaWord, Source, WordAnalysis

ADVISOR = Actor("user_advisor", Role.ADVISOR)
ADMIN = Actor("user_admin", Role.ADMIN)
LEARNER = Actor("user_learner", Role.LEARNER)


@pytest.fixture
def shloka(session: Session) -> Shloka:
    src = Source(key="test-src", kind="text", name="Test corpus", license="CC0-1.0")
    session.add(src)
    session.flush()
    s = Shloka(
        slug="test-shloka",
        title="Test",
        devanagari="तत् सवितुर्",
        iast="tat savitur",
        source_id=src.id,
        source_ref="T 1.1",
    )
    for i, (iast, deva) in enumerate([("tat", "तत्"), ("savitur", "सवितुर्")]):
        w = ShlokaWord(position=i, surface_iast=iast, surface_devanagari=deva)
        w.analyses.append(WordAnalysis(position=0, pada_iast=iast, lemma=iast, morphology={}))
        s.words.append(w)
    session.add(s)
    session.flush()
    return s


def audits(session: Session, entity_id) -> list[ContentAudit]:
    return list(
        session.scalars(
            select(ContentAudit)
            .where(ContentAudit.entity_id == entity_id)
            .order_by(ContentAudit.id)
        )
    )


def test_unverified_content_never_reaches_learners(session, shloka):
    assert list_verified_shlokas(session) == []
    assert get_verified_shloka(session, "test-shloka") is None
    assert session.execute(text("SELECT count(*) FROM verified_shlokas")).scalar() == 0


def test_only_advisors_can_verify(session, shloka):
    for actor in (ADMIN, LEARNER):
        with pytest.raises(PermissionDenied):
            verify_shloka(session, actor, "test-shloka")
    verify_shloka(session, ADVISOR, "test-shloka")
    assert [s["slug"] for s in list_verified_shlokas(session)] == ["test-shloka"]
    assert shloka.verified_by == "user_advisor"
    assert [a.action for a in audits(session, shloka.id)] == ["verify"]


def test_learners_cannot_edit(session, shloka):
    with pytest.raises(PermissionDenied):
        update_shloka(session, LEARNER, "test-shloka", {"title": "x"})


def test_edit_resets_verified_and_is_audited(session, shloka):
    verify_shloka(session, ADVISOR, "test-shloka")
    update_shloka(session, ADMIN, "test-shloka", {"translation": "That ..."})
    assert shloka.verified is False and shloka.verified_by is None
    assert get_verified_shloka(session, "test-shloka") is None
    last = audits(session, shloka.id)[-1]
    assert last.action == "update" and last.actor_clerk_id == "user_admin"
    assert last.diff == {"translation": [None, "That ..."], "verified": [True, False]}


def test_db_trigger_resets_verified_even_without_the_app(session, shloka):
    verify_shloka(session, ADVISOR, "test-shloka")
    session.execute(text("UPDATE shlokas SET iast = 'tat savituḥ' WHERE slug = 'test-shloka'"))
    assert session.execute(
        text("SELECT verified, verified_by FROM shlokas WHERE slug = 'test-shloka'")
    ).one() == (False, None)


def test_editing_words_unverifies_the_shloka_but_derived_phonemes_do_not(session, shloka):
    verify_shloka(session, ADVISOR, "test-shloka")
    session.execute(text("UPDATE shloka_words SET expected_phonemes = '[\"t\"]'"))
    session.refresh(shloka)
    assert shloka.verified is True
    session.execute(text("UPDATE shloka_words SET surface_iast = 'tad' WHERE position = 0"))
    session.refresh(shloka)
    assert shloka.verified is False


def test_review_notes_edit_does_not_unverify(session, shloka):
    verify_shloka(session, ADVISOR, "test-shloka")
    update_shloka(session, ADVISOR, "test-shloka", {"review_notes": "checked against ms."})
    assert shloka.verified is True


def test_verified_requires_reviewer(session, shloka):
    with pytest.raises(IntegrityError):
        session.execute(text("UPDATE shlokas SET verified = true WHERE slug = 'test-shloka'"))


def test_content_audit_is_append_only(session, shloka):
    verify_shloka(session, ADVISOR, "test-shloka")
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(text("DELETE FROM content_audit"))


def test_learners_only_see_verified_analyses(session, shloka):
    verify_shloka(session, ADVISOR, "test-shloka")
    first = shloka.words[0].analyses[0]
    update_word_analysis(session, ADMIN, first.id, {"meaning": "that"})
    verify_word_analysis(session, ADVISOR, first.id)
    data = get_verified_shloka(session, "test-shloka")
    assert [len(w["analyses"]) for w in data["words"]] == [1, 0]
    assert data["words"][0]["analyses"][0]["meaning"] == "that"
    assert "review_notes" not in data


def test_editing_verified_analysis_resets_it(session, shloka):
    a = shloka.words[0].analyses[0]
    with pytest.raises(PermissionDenied):
        verify_word_analysis(session, ADMIN, a.id)
    verify_word_analysis(session, ADVISOR, a.id)
    update_word_analysis(session, ADVISOR, a.id, {"explanation": "Plain-language note."})
    assert a.verified is False
    assert audits(session, a.id)[-1].diff["verified"] == [True, False]


def test_edits_are_validated(session, shloka):
    with pytest.raises(InvalidEdit):
        update_shloka(session, ADMIN, "test-shloka", {"verified": True})  # not editable
    with pytest.raises(InvalidEdit):
        update_shloka(session, ADMIN, "test-shloka", {"title": "x" * 201})
    with pytest.raises(InvalidEdit):
        update_word_analysis(session, ADMIN, shloka.words[0].analyses[0].id, {"morphology": "x"})


def test_updated_at_is_maintained(session, shloka):
    before = shloka.updated_at
    # now() is the transaction start time, so compare against a new statement timestamp
    session.execute(
        text("UPDATE shlokas SET updated_at = now() - interval '1 day' WHERE slug = 'test-shloka'")
    )
    session.refresh(shloka)
    assert shloka.updated_at >= before - dt.timedelta(seconds=1)  # trigger overrode the value


def test_one_active_reference_per_shloka(session, shloka):
    insert = text(
        "INSERT INTO audio_assets (shloka_id, kind, r2_key, is_active_reference) "
        "VALUES (:s, 'reference', :k, true)"
    )
    session.execute(insert, {"s": shloka.id, "k": "ref/a.m4a"})
    with pytest.raises(IntegrityError):
        session.execute(insert, {"s": shloka.id, "k": "ref/b.m4a"})


def test_test_recordings_need_license_and_attribution(session, shloka):
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO audio_assets (shloka_id, kind, r2_key) VALUES (:s, 'test', 'test/x')"
            ),
            {"s": shloka.id},
        )


def test_consent_must_be_recorded(session):
    with pytest.raises(IntegrityError):
        session.execute(
            text("INSERT INTO users (clerk_user_id, recording_consent) VALUES ('u1', true)")
        )
