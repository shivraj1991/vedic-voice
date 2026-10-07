"""Request bodies (Pydantic): types, lengths and enums validated at the edge.

`extra="forbid"` everywhere: unknown fields (e.g. a client sending "verified" or
"role") are rejected instead of ignored.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Slug = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80)
PlainText = str  # stored and rendered as plain text, never HTML


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConsentIn(_Body):
    recording_consent: bool
    consent_version: str | None = Field(default=None, max_length=20)


class UploadUrlIn(_Body):
    shloka_slug: str = Slug
    content_type: Literal["audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac"]
    size_bytes: int = Field(gt=0, le=2 * 1024 * 1024)


class ScoreIn(_Body):
    shloka_slug: str = Slug
    object_key: str = Field(max_length=200)


class ShlokaEditIn(_Body):
    title: str | None = Field(default=None, max_length=200)
    devanagari: str | None = Field(default=None, max_length=5000)
    iast: str | None = Field(default=None, max_length=5000)
    translation: str | None = Field(default=None, max_length=5000)
    source_ref: str | None = Field(default=None, max_length=500)
    review_notes: str | None = Field(default=None, max_length=5000)


class VerifyIn(_Body):
    notes: str | None = Field(default=None, max_length=5000)


class AnalysisEditIn(_Body):
    pada_iast: str | None = Field(default=None, max_length=200)
    lemma: str | None = Field(default=None, max_length=200)
    meaning: str | None = Field(default=None, max_length=2000)
    explanation: str | None = Field(default=None, max_length=5000)
    morphology: dict | None = None


class AssetUploadUrlIn(_Body):
    shloka_slug: str = Slug
    kind: Literal["reference", "test"]
    content_type: Literal["audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac", "audio/ogg",
                          "audio/wav", "audio/flac"]  # fmt: skip


class AssetIn(_Body):
    shloka_slug: str = Slug
    kind: Literal["reference", "test"]
    r2_key: str = Field(pattern=r"^(ref|test)/[a-z0-9-]+/[0-9a-f]{32}\.[a-z0-9]{2,4}$")
    source_url: str | None = Field(default=None, max_length=1000)
    license: str | None = Field(default=None, max_length=100)
    attribution: str | None = Field(default=None, max_length=500)
    reciter: str | None = Field(default=None, max_length=200)
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    duration_ms: int | None = Field(default=None, gt=0, le=10 * 60 * 1000)
    codec: str | None = Field(default=None, max_length=20)
    sample_rate: int | None = Field(default=None, gt=0, le=192_000)


class WordLabelIn(_Body):
    audio_asset_id: uuid.UUID
    shloka_word_id: uuid.UUID
    ok: bool
    issue_code: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=2000)
