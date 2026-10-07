"""Learner data access: users (Clerk ID only), consent, attempts.

Kept to few round trips: Lambda in Mumbai talks to Neon in Singapore.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .db.models import Attempt, AttemptWordScore, AudioAsset, Shloka, ShlokaWord, User

CONSENT_VERSIONS = {"2026-10-v1"}  # current consent text version(s) shown in the app


def get_or_create_user(session: Session, clerk_id: str) -> User:
    """One round trip: insert-if-missing, then return the row."""
    stmt = (
        insert(User)
        .values(clerk_user_id=clerk_id)
        .on_conflict_do_update(index_elements=[User.clerk_user_id],
                               set_={"clerk_user_id": clerk_id})  # no-op update returns the row
        .returning(User)
    )  # fmt: skip
    return session.scalars(stmt, execution_options={"populate_existing": True}).one()


def set_consent(session: Session, user: User, consent: bool, version: str | None) -> User:
    """Opt-in is explicit and versioned; revoking clears it (stored recordings are kept
    only while consent stands - see delete of rec/consented/ in Milestone 4 cleanup)."""
    if consent:
        if version not in CONSENT_VERSIONS:
            raise ValueError("unknown consent version")
        user.recording_consent = True
        user.consent_version = version
        user.consent_at = dt.datetime.now(dt.UTC)
    else:
        user.recording_consent = False
        user.consent_version = None
        user.consent_at = None
    session.flush()
    return user


def attempts_in_last_hour(session: Session, user_id: uuid.UUID) -> int:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
    return session.scalar(
        select(func.count()).where(Attempt.user_id == user_id, Attempt.created_at >= since)
    )


def scoring_target(
    session: Session, slug: str
) -> tuple[Shloka, list[ShlokaWord], AudioAsset] | None:
    """Verified shloka + words + its active, verified reference recording."""
    row = session.execute(
        select(Shloka, AudioAsset)
        .join(
            AudioAsset,
            (AudioAsset.shloka_id == Shloka.id)
            & AudioAsset.is_active_reference
            & AudioAsset.verified,
        )  # fmt: skip
        .where(Shloka.slug == slug, Shloka.verified)
    ).one_or_none()
    if row is None:
        return None
    shloka, ref = row
    words = list(
        session.scalars(
            select(ShlokaWord)
            .where(ShlokaWord.shloka_id == shloka.id)
            .order_by(ShlokaWord.position)
        )
    )
    return shloka, words, ref


def record_attempt(
    session: Session,
    user: User,
    shloka: Shloka,
    words: list[ShlokaWord],
    reference: AudioAsset,
    result: dict[str, Any],
) -> Attempt:
    by_pos = {w.position: w for w in words}
    attempt = Attempt(
        id=uuid.uuid4(),
        user_id=user.id,
        shloka_id=shloka.id,
        reference_audio_id=reference.id,
        overall_score=int(result["overall"]),
        scorer_version=str(result["scorer_version"])[:40],
        duration_ms=result.get("duration_ms") or None,
    )
    session.add(attempt)
    session.flush()
    session.add_all(
        AttemptWordScore(
            attempt_id=attempt.id,
            shloka_word_id=by_pos[w["position"]].id,
            score=int(w["score"]),
            issue_code=(w.get("issue_code") or None),
            issue_text=(w.get("issue_text") or None),
        )
        for w in result["words"]
        if w["position"] in by_pos
    )
    session.flush()
    return attempt


def list_attempts(session: Session, user_id: uuid.UUID, slug: str | None, limit: int) -> list[dict]:
    q = (
        select(Attempt.id, Shloka.slug, Attempt.overall_score, Attempt.created_at)
        .join(Shloka, Shloka.id == Attempt.shloka_id)
        .where(Attempt.user_id == user_id)
        .order_by(Attempt.created_at.desc())
        .limit(limit)
    )
    if slug:
        q = q.where(Shloka.slug == slug)
    return [dict(r._mapping) for r in session.execute(q)]
