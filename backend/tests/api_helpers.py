"""API test harness: app with simulated Clerk tokens, in-memory R2, fake scorer."""

from __future__ import annotations

import dataclasses
import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import text

from vv_backend.api.app import create_app
from vv_backend.api.auth import StaticJWKS
from vv_backend.api.scoring_client import FakeScorer
from vv_backend.api.settings import Settings
from vv_backend.api.storage import MemoryStorage
from vv_backend.devtools import DEV_AZP, DEV_ISSUER, make_token, new_keypair

from .conftest import session_on

KEY, JWKS = new_keypair("test-kid")
OTHER_KEY, _ = new_keypair("test-kid")  # same kid, different key -> bad signature

SETTINGS = Settings(
    env="test",
    clerk_issuer=DEV_ISSUER,
    clerk_jwks_url="https://clerk.invalid/.well-known/jwks.json",  # unused: keys injected
    authorized_parties=(DEV_AZP,),
    scoring_per_hour=5,
    upload_urls_per_minute=3,
)


def token(role: str | None = None, sub: str = "user_learner", **kw) -> str:
    return make_token(KEY, "test-kid", sub=sub, role=role, **kw)


def auth(role: str | None = None, sub: str | None = None, **kw) -> dict[str, str]:
    sub = sub or f"user_{role or 'learner'}"
    return {"Authorization": f"Bearer {token(role, sub, **kw)}"}


@dataclasses.dataclass
class Api:
    client: TestClient
    storage: MemoryStorage
    scorer: FakeScorer
    conn: object

    def sql(self, query: str, **params):
        return self.conn.execute(text(query), params)


def make_api(connection, **settings_overrides) -> Api:
    storage, scorer = MemoryStorage(), FakeScorer(weak_position=1)
    settings = dataclasses.replace(SETTINGS, **settings_overrides)
    app = create_app(
        settings,
        session_factory=lambda: session_on(connection),
        keys=StaticJWKS(JWKS),
        storage=storage,
        scorer=scorer,
    )
    return Api(TestClient(app), storage, scorer, connection)


def add_shloka(api: Api, slug: str = "tat-savitur", verified: bool = True, reference: bool = True):
    """A shloka with two words; optionally verified with an active verified reference."""
    sid = api.sql(
        "INSERT INTO sources (key, kind, name, license) VALUES (:k, 'text', 'T', 'CC0-1.0') "
        "ON CONFLICT (key) DO UPDATE SET name = 'T' RETURNING id",
        k="test-src",
    ).scalar()
    shloka_id = api.sql(
        "INSERT INTO shlokas (slug, title, devanagari, iast, source_id, source_ref) "
        "VALUES (:s, 'Test', 'तत् सवितुर्', 'tat savitur', :src, 'T 1') RETURNING id",
        s=slug,
        src=sid,
    ).scalar()
    for pos, (iast, deva) in enumerate([("tat", "तत्"), ("savitur", "सवितुर्")]):
        api.sql(
            "INSERT INTO shloka_words (shloka_id, position, surface_iast, surface_devanagari) "
            "VALUES (:s, :p, :i, :d)",
            s=shloka_id,
            p=pos,
            i=iast,
            d=deva,
        )
    if verified:
        api.sql(
            "UPDATE shlokas SET verified = true, verified_by = 'user_advisor', "
            "verified_at = :t WHERE id = :s",
            t=dt.datetime.now(dt.UTC),
            s=shloka_id,
        )
    if reference:
        key = f"ref/{slug}/{'0' * 32}.m4a"
        api.sql(
            "INSERT INTO audio_assets (shloka_id, kind, r2_key, verified, is_active_reference, "
            "duration_ms) VALUES (:s, 'reference', :k, true, true, 4000)",
            s=shloka_id,
            k=key,
        )
        api.storage.put("reference", key, 50_000)
    return shloka_id
