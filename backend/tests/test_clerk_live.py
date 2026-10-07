"""Live check against the real Clerk development instance (opt-in: VV_LIVE_CLERK=1).

Needs network access to the Clerk Frontend API host. Verifies we can fetch and
parse the real JWKS, and that a token forged with Clerk's key id is rejected.
"""

import os
from pathlib import Path

import pytest

from vv_backend.api.auth import AuthError, ClerkJWKS, verify_token
from vv_backend.api.settings import Settings
from vv_backend.devtools import make_token, new_keypair

CONFIG = Path(__file__).resolve().parents[1] / "config" / "clerk.dev.public.env"

pytestmark = pytest.mark.skipif(os.environ.get("VV_LIVE_CLERK") != "1", reason="VV_LIVE_CLERK!=1")


def _settings() -> Settings:
    env = dict(
        line.split("=", 1)
        for line in CONFIG.read_text().splitlines()
        if line and not line.startswith("#")
    )
    return Settings(
        env="dev",
        clerk_issuer=env["CLERK_ISSUER"],
        clerk_jwks_url=env["CLERK_JWKS_URL"],
        authorized_parties=tuple(env["CLERK_AUTHORIZED_PARTIES"].split(",")),
        allow_missing_azp=env["CLERK_ALLOW_MISSING_AZP"] == "true",
    )


def test_real_jwks_and_forgery_rejected():
    import jwt

    settings = _settings()
    keys = jwt.PyJWKClient(settings.clerk_jwks_url).get_signing_keys()
    assert keys and all(k.key.key_size >= 2048 for k in keys)
    forged_key, _ = new_keypair()
    forged = make_token(forged_key, keys[0].key_id, issuer=settings.clerk_issuer, role="admin",
                        azp=None)  # fmt: skip
    with pytest.raises(AuthError):
        verify_token(forged, settings, ClerkJWKS(settings.clerk_jwks_url))
