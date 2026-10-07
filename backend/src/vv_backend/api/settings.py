"""API settings from the environment. No defaults for secrets: fail fast if missing.

`VV_ENV` must be set explicitly (dev | test | prod). Dev-only conveniences (a
local signing key instead of Clerk's JWKS) are refused when VV_ENV=prod.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class SettingsError(RuntimeError):
    pass


def _req(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SettingsError(f"{name} is not set")
    return value


def _list(name: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in os.environ.get(name, "").split(",") if x.strip())


@dataclass(frozen=True)
class R2Settings:
    account_id: str
    bucket_reference: str  # ref/ and test/ audio
    bucket_recordings: str  # rec/tmp/ and rec/consented/
    read_key_id: str
    read_secret: str
    write_key_id: str
    write_secret: str


@dataclass(frozen=True)
class Settings:
    env: str
    clerk_issuer: str
    clerk_jwks_url: str | None
    authorized_parties: tuple[str, ...]
    cors_origins: tuple[str, ...] = ()
    # Clerk omits `azp` when the request had no browser Origin (native iOS/Android).
    # True: tokens without azp are accepted; a *present* azp must still match.
    allow_missing_azp: bool = False
    dev_jwks_path: str | None = None  # dev only: JWKS file from `vv_backend.devtools`
    r2: R2Settings | None = None
    scoring_function: str | None = None
    aws_region: str | None = None
    # Limits (SECURITY.md: uploads <= 2 MB / 60 s; rate limits on scoring/upload URLs)
    max_upload_bytes: int = 2 * 1024 * 1024
    signed_url_seconds: int = 600  # <= 15 min
    scoring_per_hour: int = 30
    upload_urls_per_minute: int = 10
    allowed_audio_types: tuple[str, ...] = field(
        default=("audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac")
    )

    def __post_init__(self) -> None:
        if self.env not in {"dev", "test", "prod"}:
            raise SettingsError("VV_ENV must be dev, test or prod")
        if self.env == "prod" and self.dev_jwks_path:
            raise SettingsError("VV_DEV_JWKS_PATH is not allowed in prod")
        if not (self.clerk_jwks_url or self.dev_jwks_path):
            raise SettingsError("CLERK_JWKS_URL is not set")
        if not self.authorized_parties:
            raise SettingsError("CLERK_AUTHORIZED_PARTIES is not set")
        if self.signed_url_seconds > 900:
            raise SettingsError("signed URLs must expire within 15 minutes")
        if "*" in self.cors_origins:
            raise SettingsError("CORS origins must be explicit, not *")

    @classmethod
    def from_env(cls) -> Settings:
        r2 = None
        if os.environ.get("R2_ACCOUNT_ID"):
            r2 = R2Settings(
                account_id=_req("R2_ACCOUNT_ID"),
                bucket_reference=_req("R2_BUCKET_REFERENCE"),
                bucket_recordings=_req("R2_BUCKET_RECORDINGS"),
                read_key_id=_req("R2_READ_ACCESS_KEY_ID"),
                read_secret=_req("R2_READ_SECRET_ACCESS_KEY"),
                write_key_id=_req("R2_WRITE_ACCESS_KEY_ID"),
                write_secret=_req("R2_WRITE_SECRET_ACCESS_KEY"),
            )
        return cls(
            env=_req("VV_ENV"),
            clerk_issuer=_req("CLERK_ISSUER"),
            clerk_jwks_url=os.environ.get("CLERK_JWKS_URL") or None,
            authorized_parties=_list("CLERK_AUTHORIZED_PARTIES"),
            allow_missing_azp=os.environ.get("CLERK_ALLOW_MISSING_AZP", "").lower() == "true",
            cors_origins=_list("CORS_ORIGINS"),
            dev_jwks_path=os.environ.get("VV_DEV_JWKS_PATH") or None,
            r2=r2,
            scoring_function=os.environ.get("SCORING_FUNCTION_NAME") or None,
            aws_region=os.environ.get("AWS_REGION") or None,
        )
