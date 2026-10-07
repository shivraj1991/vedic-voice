"""Admin/advisor routes (console, Milestone 3b). Every route needs role admin or
advisor; anything that sets `verified` needs advisor. Roles come from the token."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from .. import audio, content
from .auth import Advisor, Staff
from .deps import DB, AppSettings, AudioStorage
from .schemas import AnalysisEditIn, AssetIn, AssetUploadUrlIn, ShlokaEditIn, VerifyIn, WordLabelIn
from .storage import new_asset_key

router = APIRouter(prefix="/admin")
EXT = {"audio/mp4": "m4a", "audio/m4a": "m4a", "audio/x-m4a": "m4a", "audio/aac": "aac",
       "audio/ogg": "ogg", "audio/wav": "wav", "audio/flac": "flac"}  # fmt: skip


def _changes(body) -> dict:
    return body.model_dump(exclude_unset=True)


@router.get("/shlokas")
def list_shlokas(_: Staff, db: DB) -> list[dict]:
    return content.admin_list_shlokas(db)


@router.get("/shlokas/{slug}")
def get_shloka(slug: str, _: Staff, db: DB) -> dict:
    return content.admin_get_shloka(db, slug)


@router.patch("/shlokas/{slug}")
def edit_shloka(slug: str, body: ShlokaEditIn, staff: Staff, db: DB) -> dict:
    content.update_shloka(db, staff.actor, slug, _changes(body))
    return content.admin_get_shloka(db, slug)


@router.post("/shlokas/{slug}/verify")
def verify_shloka(slug: str, body: VerifyIn, advisor: Advisor, db: DB) -> dict:
    content.verify_shloka(db, advisor.actor, slug, body.notes)
    return content.admin_get_shloka(db, slug)


@router.patch("/word-analyses/{analysis_id}")
def edit_analysis(analysis_id: uuid.UUID, body: AnalysisEditIn, staff: Staff, db: DB) -> dict:
    a = content.update_word_analysis(db, staff.actor, analysis_id, _changes(body))
    return {"id": a.id, "verified": a.verified}


@router.post("/word-analyses/{analysis_id}/verify")
def verify_analysis(analysis_id: uuid.UUID, advisor: Advisor, db: DB) -> dict:
    a = content.verify_word_analysis(db, advisor.actor, analysis_id)
    return {"id": a.id, "verified": a.verified}


@router.get("/audit")
def audit_log(_: Staff, db: DB, entity_id: uuid.UUID | None = None,
              limit: int = Query(default=100, ge=1, le=500)) -> list[dict]:  # fmt: skip
    return content.list_audit(db, entity_id, limit)


# --- recordings -----------------------------------------------------------------


@router.post("/audio/upload-url")
def asset_upload_url(body: AssetUploadUrlIn, _: Staff, storage: AudioStorage,
                     settings: AppSettings) -> dict:  # fmt: skip
    key = new_asset_key(body.kind, body.shloka_slug, EXT[body.content_type])
    signed = storage.presign_put("reference", key, body.content_type, settings.signed_url_seconds)
    return {"url": signed.url, "method": signed.method, "headers": signed.headers,
            "r2_key": key, "expires_in": signed.expires_in}  # fmt: skip


def _asset_view(a) -> dict:
    return {"id": a.id, "shloka_id": a.shloka_id, "kind": a.kind, "r2_key": a.r2_key,
            "license": a.license, "attribution": a.attribution, "reciter": a.reciter,
            "source_url": a.source_url, "duration_ms": a.duration_ms, "verified": a.verified,
            "is_active_reference": a.is_active_reference, "created_at": a.created_at}  # fmt: skip


@router.post("/audio", status_code=status.HTTP_201_CREATED)
def register_audio(body: AssetIn, staff: Staff, db: DB, storage: AudioStorage) -> dict:
    if not body.r2_key.startswith({"reference": "ref/", "test": "test/"}[body.kind]):
        raise HTTPException(422, "key prefix does not match kind")
    if storage.head("reference", body.r2_key) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "upload the file first")
    meta = body.model_dump(exclude={"shloka_slug", "kind", "r2_key"})
    asset = audio.register_asset(db, staff.actor, body.shloka_slug, body.kind, body.r2_key, meta)
    return _asset_view(asset)


@router.get("/audio")
def list_audio(_: Staff, db: DB, shloka: str | None = Query(default=None, max_length=80)) -> list:
    return [_asset_view(a) for a in audio.list_assets(db, shloka)]


@router.get("/audio/{asset_id}/play-url")
def play_url(asset_id: uuid.UUID, _: Staff, db: DB, storage: AudioStorage,
             settings: AppSettings) -> dict:  # fmt: skip
    asset = audio.get_asset(db, asset_id)
    signed = storage.presign_get("reference", asset.r2_key, settings.signed_url_seconds)
    return {"url": signed.url, "expires_in": signed.expires_in}


@router.post("/audio/{asset_id}/verify")
def verify_audio(asset_id: uuid.UUID, advisor: Advisor, db: DB) -> dict:
    return _asset_view(audio.verify_asset(db, advisor.actor, asset_id))


@router.post("/audio/{asset_id}/activate")
def activate_audio(asset_id: uuid.UUID, staff: Staff, db: DB) -> dict:
    return _asset_view(audio.activate_reference(db, staff.actor, asset_id))


@router.put("/word-labels", status_code=status.HTTP_204_NO_CONTENT)
def put_label(body: WordLabelIn, staff: Staff, db: DB) -> None:
    audio.upsert_label(db, staff.actor, body.audio_asset_id, body.shloka_word_id, body.ok,
                       body.issue_code, body.note)  # fmt: skip
