"""Signed-in learner routes: profile/consent, reference audio, upload, scoring, history."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from ..db.models import AudioAsset, AudioWordMark, Shloka, ShlokaWord
from ..learners import (
    attempts_in_last_hour,
    get_or_create_user,
    list_attempts,
    record_attempt,
    scoring_target,
    set_consent,
)
from .auth import CurrentPrincipal
from .deps import DB, AppSettings, AudioStorage, ScoringService
from .schemas import ConsentIn, ScoreIn, UploadUrlIn
from .scoring_client import ScoringError
from .storage import TMP_KEY, consented_key, new_recording_key

log = logging.getLogger(__name__)
router = APIRouter()
LOW_MATCH = 0.88  # spike: keeps 95% of correct recitations, rejects wrong-text audio


def _user_view(user) -> dict:
    return {"id": user.id, "recording_consent": user.recording_consent,
            "consent_version": user.consent_version, "timezone": user.timezone}  # fmt: skip


@router.get("/me")
def me(principal: CurrentPrincipal, db: DB) -> dict:
    user = get_or_create_user(db, principal.clerk_id)
    return _user_view(user) | {"role": principal.role.value}


@router.put("/me/consent")
def consent(body: ConsentIn, principal: CurrentPrincipal, db: DB) -> dict:
    user = get_or_create_user(db, principal.clerk_id)
    try:
        set_consent(db, user, body.recording_consent, body.consent_version)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return _user_view(user)


@router.get("/shlokas/{slug}/reference-audio")
def reference_audio(slug: str, principal: CurrentPrincipal, db: DB, storage: AudioStorage,
                    settings: AppSettings) -> dict:  # fmt: skip
    """Signed GET for the active, verified reference recording + word timings."""
    asset = db.scalar(
        select(AudioAsset)
        .join(Shloka, Shloka.id == AudioAsset.shloka_id)
        .where(
            Shloka.slug == slug,
            Shloka.verified,
            AudioAsset.is_active_reference,
            AudioAsset.verified,
        )  # fmt: skip
    )
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no reference recording")
    marks = db.execute(
        select(ShlokaWord.position, AudioWordMark.start_ms, AudioWordMark.end_ms)
        .join(ShlokaWord, ShlokaWord.id == AudioWordMark.shloka_word_id)
        .where(AudioWordMark.audio_asset_id == asset.id)
        .order_by(ShlokaWord.position)
    )
    signed = storage.presign_get("reference", asset.r2_key, settings.signed_url_seconds)
    return {"url": signed.url, "expires_in": signed.expires_in, "duration_ms": asset.duration_ms,
            "reciter": asset.reciter, "word_marks": [dict(m._mapping) for m in marks]}  # fmt: skip


@router.post("/recordings/upload-url")
def upload_url(body: UploadUrlIn, request: Request, principal: CurrentPrincipal, db: DB,
               storage: AudioStorage, settings: AppSettings) -> dict:  # fmt: skip
    """Signed PUT to a server-chosen key under the learner's own tmp prefix."""
    request.app.state.upload_limiter.check(principal.clerk_id)
    if db.scalar(select(Shloka.id).where(Shloka.slug == body.shloka_slug, Shloka.verified)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    user = get_or_create_user(db, principal.clerk_id)
    key = new_recording_key(user.id)
    signed = storage.presign_put("recordings", key, body.content_type, settings.signed_url_seconds)
    return {"url": signed.url, "method": signed.method, "headers": signed.headers,
            "object_key": key, "expires_in": signed.expires_in,
            "max_bytes": settings.max_upload_bytes}  # fmt: skip


@router.post("/score-pronunciation")
def score_pronunciation(body: ScoreIn, principal: CurrentPrincipal, db: DB, storage: AudioStorage,
                        scorer: ScoringService, settings: AppSettings) -> dict:  # fmt: skip
    user = get_or_create_user(db, principal.clerk_id)
    m = TMP_KEY.match(body.object_key)
    if m is None or m["user"] != str(user.id):  # only the caller's own uploads
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your recording")
    if attempts_in_last_hour(db, user.id) >= settings.scoring_per_hour:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "scoring limit reached, try later")
    target = scoring_target(db, body.shloka_slug)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "shloka or reference recording not found")
    shloka, words, reference = target

    info = storage.head("recordings", body.object_key)
    if info is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recording not uploaded")
    if info.size > settings.max_upload_bytes or (
        info.content_type and info.content_type not in settings.allowed_audio_types
    ):
        storage.delete("recordings", body.object_key)
        raise HTTPException(413, "recording too large or wrong format")

    request = {
        "recording": {"bucket": "recordings", "key": body.object_key},
        "reference": {"bucket": "reference", "key": reference.r2_key},
        "text_iast": shloka.iast,
        "words": [{"position": w.position, "surface_iast": w.surface_iast} for w in words],
    }
    try:
        result = scorer.score(request)
    except ScoringError as e:
        storage.delete("recordings", body.object_key)
        log.warning("scoring failed: %s", e.code)  # no keys/URLs in logs
        raise HTTPException(422, f"could not score: {e.code}") from e

    attempt = record_attempt(db, user, shloka, words, reference, result)
    if user.recording_consent:
        dst = consented_key(user.id, attempt.id)
        storage.copy("recordings", body.object_key, dst)
        attempt.recording_r2_key = dst
    storage.delete("recordings", body.object_key)  # tmp copy never kept (lifecycle is the backstop)

    by_pos = {w["position"]: w for w in result["words"]}
    low_match = float(result["match_confidence"]) < LOW_MATCH
    return {
        "attempt_id": attempt.id,
        "overall": attempt.overall_score,
        "match_confidence": result["match_confidence"],
        "low_match": low_match,
        "message": "We couldn't match your chant to this shloka. Try again?" if low_match else None,
        "words": [
            {"position": w.position, "surface_iast": w.surface_iast,
             "surface_devanagari": w.surface_devanagari,
             "score": by_pos.get(w.position, {}).get("score"),
             "issue_code": by_pos.get(w.position, {}).get("issue_code"),
             "issue_text": by_pos.get(w.position, {}).get("issue_text"),
             "start_ms": by_pos.get(w.position, {}).get("start_ms"),
             "end_ms": by_pos.get(w.position, {}).get("end_ms")}
            for w in words
        ],
    }  # fmt: skip


@router.get("/me/attempts")
def my_attempts(principal: CurrentPrincipal, db: DB,
                shloka: str | None = Query(default=None, max_length=80),
                limit: int = Query(default=20, ge=1, le=100)) -> list[dict]:  # fmt: skip
    user = get_or_create_user(db, principal.clerk_id)
    return list_attempts(db, user.id, shloka, limit)
