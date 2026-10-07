"""Clerk token checks (SECURITY.md: missing, expired, wrong issuer, wrong role...)."""

import time

import pytest

from vv_backend.api.settings import Settings, SettingsError
from vv_backend.devtools import make_token

from .api_helpers import OTHER_KEY, SETTINGS, auth


def bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def test_missing_and_malformed_tokens(api):
    assert api.client.get("/me").status_code == 401
    assert api.client.get("/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert api.client.get("/me", headers={"Authorization": "Basic abc"}).status_code == 401
    r = api.client.get("/me")
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "kw",
    [
        {"now": time.time() - 7200, "ttl_s": 60},  # expired
        {"issuer": "https://evil.clerk.accounts.dev"},  # wrong issuer
        {"azp": "https://evil.example"},  # unauthorized party
        {"now": time.time() + 3600},  # not yet valid (nbf/iat in the future)
    ],
)
def test_invalid_claims_are_rejected(api, kw):
    assert api.client.get("/me", headers=auth(**kw)).status_code == 401


def test_bad_signature_is_rejected(api):
    forged = make_token(OTHER_KEY, "test-kid", sub="user_x", role="advisor")
    assert api.client.get("/me", headers=bearer(forged)).status_code == 401


def test_valid_token_and_role_from_token_only(api):
    r = api.client.get("/me", headers=auth())
    assert r.status_code == 200 and r.json()["role"] == "learner"
    r = api.client.get("/me", headers=auth("advisor"))
    assert r.json()["role"] == "advisor"
    # unknown role claims degrade to learner
    assert api.client.get("/me", headers=auth("superuser")).json()["role"] == "learner"


def test_role_gates(api):
    assert api.client.get("/admin/shlokas", headers=auth()).status_code == 403
    assert api.client.get("/admin/shlokas", headers=auth("admin")).status_code == 200
    assert api.client.get("/admin/shlokas", headers=auth("advisor")).status_code == 200
    assert api.client.get("/admin/shlokas").status_code == 401


def test_every_non_public_route_requires_a_token(api):
    from vv_backend.api.routes_public import PUBLIC_PATHS

    paths = api.client.get("/openapi.json").json()["paths"]
    assert len(paths) > 15
    for path, ops in paths.items():
        if path in PUBLIC_PATHS:
            continue
        url = path.replace("{slug}", "x").replace("{analysis_id}", "0" * 32)
        url = url.replace("{asset_id}", "0" * 32)
        for method in ops:
            r = api.client.request(method.upper(), url)
            assert r.status_code == 401, (method, path, r.status_code)


def test_settings_safety_rails():
    import dataclasses

    with pytest.raises(SettingsError):
        dataclasses.replace(SETTINGS, env="prod", dev_jwks_path=".dev-keys/jwks.json")
    with pytest.raises(SettingsError):
        dataclasses.replace(SETTINGS, cors_origins=("*",))
    with pytest.raises(SettingsError):
        dataclasses.replace(SETTINGS, signed_url_seconds=3600)
    with pytest.raises(SettingsError):
        Settings(env="prod", clerk_issuer="x", clerk_jwks_url=None, authorized_parties=("a",))
