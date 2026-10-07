"""Audio asset data access (reference and test recordings, word labels).

Reference audio is content: making a recording the *active* reference for
learners needs an advisor-verified asset, and every change is audited.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .content import Actor, InvalidEdit, NotFound, Role, audit, require_role
from .db.models import AudioAsset, Shloka, ShlokaWord, WordLabel

ASSET_FIELDS = ("source_url", "license", "attribution", "reciter", "sha256", "duration_ms",
                "codec", "sample_rate")  # fmt: skip


def get_asset(session: Session, asset_id: uuid.UUID) -> AudioAsset:
    asset = session.get(AudioAsset, asset_id)
    if asset is None:
        raise NotFound(str(asset_id))
    return asset


def register_asset(
    session: Session, actor: Actor, slug: str, kind: str, r2_key: str, meta: dict[str, Any]
) -> AudioAsset:
    require_role(actor, Role.ADMIN, Role.ADVISOR)
    if kind not in {"reference", "test"}:
        raise InvalidEdit("kind must be reference or test")
    if kind == "test" and not (meta.get("license") and meta.get("attribution")):
        raise InvalidEdit("test recordings need a license and attribution")
    shloka = session.scalar(select(Shloka).where(Shloka.slug == slug))
    if shloka is None:
        raise NotFound(slug)
    asset = AudioAsset(shloka_id=shloka.id, kind=kind, r2_key=r2_key,
                       **{k: meta.get(k) for k in ASSET_FIELDS})  # fmt: skip
    session.add(asset)
    session.flush()
    audit(session, actor, "audio_asset", asset.id, "create",
          {"shloka": slug, "kind": kind, "r2_key": r2_key, "license": asset.license})  # fmt: skip
    return asset


def list_assets(session: Session, slug: str | None) -> list[AudioAsset]:
    q = select(AudioAsset).order_by(AudioAsset.created_at.desc())
    if slug:
        q = q.join(Shloka, Shloka.id == AudioAsset.shloka_id).where(Shloka.slug == slug)
    return list(session.scalars(q))


def verify_asset(session: Session, actor: Actor, asset_id: uuid.UUID) -> AudioAsset:
    require_role(actor, Role.ADVISOR)
    asset = get_asset(session, asset_id)
    if not asset.verified:
        asset.verified = True
        session.flush()
        audit(session, actor, "audio_asset", asset.id, "verify", {"verified": [False, True]})
    return asset


def activate_reference(session: Session, actor: Actor, asset_id: uuid.UUID) -> AudioAsset:
    """Make a verified reference recording the one learners hear and are scored against."""
    require_role(actor, Role.ADMIN, Role.ADVISOR)
    asset = get_asset(session, asset_id)
    if asset.kind != "reference" or not asset.verified:
        raise InvalidEdit("only an advisor-verified reference recording can be activated")
    previous = session.scalar(
        select(AudioAsset).where(
            AudioAsset.shloka_id == asset.shloka_id, AudioAsset.is_active_reference
        )  # fmt: skip
    )
    if previous is not None and previous.id != asset.id:
        previous.is_active_reference = False
        session.flush()
    asset.is_active_reference = True
    session.flush()
    audit(session, actor, "audio_asset", asset.id, "activate",
          {"previous": str(previous.id) if previous else None})  # fmt: skip
    return asset


def upsert_label(
    session: Session,
    actor: Actor,
    asset_id: uuid.UUID,
    word_id: uuid.UUID,
    ok: bool,
    issue_code: str | None,
    note: str | None,
) -> None:
    """Advisor ground truth for scoring evaluation (one label per labeler per word)."""
    require_role(actor, Role.ADMIN, Role.ADVISOR)
    asset = get_asset(session, asset_id)
    word = session.get(ShlokaWord, word_id)
    if word is None or word.shloka_id != asset.shloka_id:
        raise InvalidEdit("word does not belong to this recording's shloka")
    values = {"audio_asset_id": asset_id, "shloka_word_id": word_id, "ok": ok,
              "issue_code": issue_code, "note": note, "labeled_by": actor.clerk_id}  # fmt: skip
    session.execute(
        insert(WordLabel)
        .values(**values)
        .on_conflict_do_update(
            constraint="uq_word_labels_per_labeler",
            set_={"ok": ok, "issue_code": issue_code, "note": note},
        )
    )
