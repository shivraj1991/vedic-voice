"""Public, read-only routes: the only endpoints without a Clerk session (SECURITY.md
allowlist). They return verified content only."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..content import get_verified_shloka, list_verified_shlokas
from .deps import DB

router = APIRouter()

PUBLIC_PATHS = {"/health", "/shlokas", "/shlokas/{slug}"}


@router.get("/health")
def health() -> dict:
    return {"ok": True}


@router.get("/shlokas")
def shlokas(db: DB) -> list[dict]:
    return list_verified_shlokas(db)


@router.get("/shlokas/{slug}")
def shloka(slug: str, db: DB) -> dict:
    data = get_verified_shloka(db, slug)
    if data is None:  # unverified and missing look the same to learners
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return data
