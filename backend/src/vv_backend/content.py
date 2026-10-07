"""Content data access: the only place that changes shlokas and word analyses.

Rules enforced here (the DB enforces the rest, see migration 0001):
- Learner reads use the `verified_shlokas` view and only verified analyses.
- Edits need role admin or advisor; setting verified needs advisor. The role
  comes from the verified Clerk token (Milestone 2), never from request data.
- Every change writes a `content_audit` row with a before/after diff.
- Edit inputs are whitelisted and length-limited plain text.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, MetaData, String, Table, Text, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Session, selectinload

from .db.models import ContentAudit, Shloka, ShlokaWord, WordAnalysis


class Role(StrEnum):
    ADMIN = "admin"
    ADVISOR = "advisor"
    LEARNER = "learner"


@dataclass(frozen=True)
class Actor:
    clerk_id: str
    role: Role


SYSTEM_SEED = Actor("system:seed", Role.ADMIN)


class PermissionDenied(Exception):
    pass


class NotFound(Exception):
    pass


class InvalidEdit(ValueError):
    pass


# The view is created by migration 0001; declared here (outside Base.metadata) for queries.
verified_shlokas = Table(
    "verified_shlokas",
    MetaData(),
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("slug", String),
    Column("title", String),
    Column("devanagari", Text),
    Column("iast", Text),
    Column("translation", Text),
    Column("source_id", UUID(as_uuid=True)),
    Column("source_ref", Text),
    Column("verified_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True)),
)

SHLOKA_EDITABLE = {
    "title": 200,
    "devanagari": 5000,
    "iast": 5000,
    "translation": 5000,
    "source_ref": 500,
    "review_notes": 5000,
}
ANALYSIS_EDITABLE = {
    "pada_iast": 200,
    "lemma": 200,
    "meaning": 2000,
    "explanation": 5000,
    "morphology": None,  # JSON object; validated for type only
}


def require_role(actor: Actor, *roles: Role) -> None:
    if actor.role not in roles:
        raise PermissionDenied(f"role {actor.role} may not do this")


def _validate(changes: dict[str, Any], allowed: dict[str, int | None]) -> None:
    unknown = set(changes) - set(allowed)
    if unknown:
        raise InvalidEdit(f"fields not editable: {sorted(unknown)}")
    for field, value in changes.items():
        limit = allowed[field]
        if limit is None:
            if not isinstance(value, dict):
                raise InvalidEdit(f"{field} must be an object")
            continue
        if value is not None and (not isinstance(value, str) or len(value) > limit):
            raise InvalidEdit(f"{field} must be text of at most {limit} characters")


def audit(
    session: Session,
    actor: Actor,
    entity: str,
    entity_id: uuid.UUID,
    action: str,
    diff: dict[str, Any] | None = None,
) -> None:
    session.add(
        ContentAudit(
            actor_clerk_id=actor.clerk_id,
            entity=entity,
            entity_id=entity_id,
            action=action,
            diff=diff or {},
        )
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID | dt.datetime | dt.date):
        return str(value)
    return value


# --- learner reads (verified only) -------------------------------------------


def list_verified_shlokas(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            verified_shlokas.c.slug, verified_shlokas.c.title, verified_shlokas.c.devanagari
        ).order_by(verified_shlokas.c.title)
    )
    return [dict(r._mapping) for r in rows]


def get_verified_shloka(session: Session, slug: str) -> dict[str, Any] | None:
    """A verified shloka with its words and their *verified* analyses (2 round trips)."""
    row = session.execute(
        select(verified_shlokas).where(verified_shlokas.c.slug == slug)
    ).one_or_none()
    if row is None:
        return None
    words = session.scalars(
        select(ShlokaWord)
        .where(ShlokaWord.shloka_id == row.id)
        .order_by(ShlokaWord.position)
        .options(selectinload(ShlokaWord.analyses))
    ).all()
    out = {k: v for k, v in row._mapping.items() if k not in {"id", "source_id"}}
    out["words"] = [
        {
            "position": w.position,
            "surface_iast": w.surface_iast,
            "surface_devanagari": w.surface_devanagari,
            "analyses": [
                {
                    "pada_iast": a.pada_iast,
                    "lemma": a.lemma,
                    "meaning": a.meaning,
                    "explanation": a.explanation,
                    "morphology": a.morphology.get("chosen") or a.morphology.get("proposed"),
                }  # fmt: skip
                for a in w.analyses
                if a.verified
            ],
        }
        for w in words
    ]
    return out


# --- admin / advisor writes ----------------------------------------------------


def _shloka(session: Session, slug: str) -> Shloka:
    shloka = session.scalar(select(Shloka).where(Shloka.slug == slug))
    if shloka is None:
        raise NotFound(slug)
    return shloka


def update_shloka(session: Session, actor: Actor, slug: str, changes: dict[str, Any]) -> Shloka:
    """Edit shloka fields. A verified shloka becomes unverified (DB trigger)."""
    require_role(actor, Role.ADMIN, Role.ADVISOR)
    _validate(changes, SHLOKA_EDITABLE)
    shloka = _shloka(session, slug)
    was_verified = shloka.verified
    diff = {}
    for field, value in changes.items():
        old = getattr(shloka, field)
        if old != value:
            diff[field] = [old, value]
            setattr(shloka, field, value)
    if not diff:
        return shloka
    session.flush()
    session.refresh(shloka)
    if was_verified and not shloka.verified:
        diff["verified"] = [True, False]
    audit(session, actor, "shloka", shloka.id, "update", diff)
    return shloka


def verify_shloka(session: Session, actor: Actor, slug: str, notes: str | None = None) -> Shloka:
    """Mark a shloka verified. Advisors only."""
    require_role(actor, Role.ADVISOR)
    shloka = _shloka(session, slug)
    if shloka.verified:
        return shloka
    if notes is not None:
        _validate({"review_notes": notes}, SHLOKA_EDITABLE)
        shloka.review_notes = notes
    shloka.verified = True
    shloka.verified_by = actor.clerk_id
    shloka.verified_at = dt.datetime.now(dt.UTC)
    session.flush()
    audit(session, actor, "shloka", shloka.id, "verify", {"verified": [False, True]})
    return shloka


def update_word_analysis(
    session: Session, actor: Actor, analysis_id: uuid.UUID, changes: dict[str, Any]
) -> WordAnalysis:
    require_role(actor, Role.ADMIN, Role.ADVISOR)
    _validate(changes, ANALYSIS_EDITABLE)
    analysis = session.get(WordAnalysis, analysis_id)
    if analysis is None:
        raise NotFound(str(analysis_id))
    was_verified = analysis.verified
    diff = {}
    for field, value in changes.items():
        old = getattr(analysis, field)
        if old != value:
            diff[field] = [_jsonable(old), _jsonable(value)]
            setattr(analysis, field, value)
    if not diff:
        return analysis
    session.flush()
    session.refresh(analysis)
    if was_verified and not analysis.verified:
        diff["verified"] = [True, False]
    audit(session, actor, "word_analysis", analysis.id, "update", diff)
    return analysis


def verify_word_analysis(session: Session, actor: Actor, analysis_id: uuid.UUID) -> WordAnalysis:
    require_role(actor, Role.ADVISOR)
    analysis = session.get(WordAnalysis, analysis_id)
    if analysis is None:
        raise NotFound(str(analysis_id))
    if not analysis.verified:
        analysis.verified = True
        analysis.verified_by = actor.clerk_id
        analysis.verified_at = dt.datetime.now(dt.UTC)
        session.flush()
        audit(session, actor, "word_analysis", analysis.id, "verify", {"verified": [False, True]})
    return analysis


__all__ = [
    "Actor",
    "InvalidEdit",
    "NotFound",
    "PermissionDenied",
    "Role",
    "admin_get_shloka",
    "admin_list_shlokas",
    "audit",
    "list_audit",
    "require_role",
    "get_verified_shloka",
    "list_verified_shlokas",
    "update_shloka",
    "update_word_analysis",
    "verify_shloka",
    "verify_word_analysis",
]


# --- admin / advisor reads (everything, including unverified drafts) -------------


def admin_list_shlokas(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Shloka.slug, Shloka.title, Shloka.verified, Shloka.verified_at, Shloka.updated_at)
        .order_by(Shloka.title)
    )  # fmt: skip
    return [dict(r._mapping) for r in rows]


def admin_get_shloka(session: Session, slug: str) -> dict[str, Any]:
    shloka = session.scalar(
        select(Shloka)
        .where(Shloka.slug == slug)
        .options(
            selectinload(Shloka.words).selectinload(ShlokaWord.analyses),
            selectinload(Shloka.source),
        )  # fmt: skip
    )
    if shloka is None:
        raise NotFound(slug)
    return {
        "slug": shloka.slug, "title": shloka.title, "devanagari": shloka.devanagari,
        "iast": shloka.iast, "translation": shloka.translation, "source_ref": shloka.source_ref,
        "source": {"key": shloka.source.key, "name": shloka.source.name,
                   "license": shloka.source.license, "url": shloka.source.url},
        "verified": shloka.verified, "verified_by": shloka.verified_by,
        "verified_at": shloka.verified_at, "review_notes": shloka.review_notes,
        "updated_at": shloka.updated_at,
        "words": [
            {"id": w.id, "position": w.position, "surface_iast": w.surface_iast,
             "surface_devanagari": w.surface_devanagari,
             "analyses": [
                 {"id": a.id, "position": a.position, "pada_iast": a.pada_iast, "lemma": a.lemma,
                  "morphology": a.morphology, "meaning": a.meaning, "explanation": a.explanation,
                  "analysis_tool": a.analysis_tool, "verified": a.verified,
                  "verified_by": a.verified_by}
                 for a in w.analyses
             ]}
            for w in shloka.words
        ],
    }  # fmt: skip


def list_audit(
    session: Session, entity_id: uuid.UUID | None, limit: int = 100
) -> list[dict[str, Any]]:
    q = select(ContentAudit).order_by(ContentAudit.id.desc()).limit(limit)
    if entity_id:
        q = q.where(ContentAudit.entity_id == entity_id)
    return [
        {"id": a.id, "actor": a.actor_clerk_id, "entity": a.entity, "entity_id": a.entity_id,
         "action": a.action, "diff": a.diff, "at": a.at}
        for a in session.scalars(q)
    ]  # fmt: skip
