"""Public and learner routes, including the full upload -> score flow."""

from .api_helpers import add_shloka, auth, make_api


def upload(api, slug="tat-savitur", headers=None, size=40_000):
    r = api.client.post(
        "/recordings/upload-url",
        headers=headers or auth(),
        json={"shloka_slug": slug, "content_type": "audio/mp4", "size_bytes": size},
    )
    assert r.status_code == 200, r.text
    key = r.json()["object_key"]
    api.storage.put("recordings", key, size)  # what the app's PUT would do
    return key


def test_public_routes_only_show_verified(api):
    add_shloka(api, "verified-one")
    add_shloka(api, "draft-one", verified=False)
    assert api.client.get("/health").json() == {"ok": True}
    assert [s["slug"] for s in api.client.get("/shlokas").json()] == ["verified-one"]
    detail = api.client.get("/shlokas/verified-one").json()
    assert [w["surface_iast"] for w in detail["words"]] == ["tat", "savitur"]
    assert "review_notes" not in detail and "verified_by" not in detail
    assert api.client.get("/shlokas/draft-one").status_code == 404


def test_me_creates_user_once_and_consent_is_versioned(api):
    a = api.client.get("/me", headers=auth()).json()
    b = api.client.get("/me", headers=auth()).json()
    assert a["id"] == b["id"] and a["recording_consent"] is False
    bad = api.client.put(
        "/me/consent", headers=auth(), json={"recording_consent": True, "consent_version": "v0"}
    )
    assert bad.status_code == 422
    ok = api.client.put(
        "/me/consent",
        headers=auth(),
        json={"recording_consent": True, "consent_version": "2026-10-v1"},
    )
    assert ok.json()["recording_consent"] is True
    off = api.client.put("/me/consent", headers=auth(), json={"recording_consent": False})
    assert off.json()["consent_version"] is None


def test_upload_url_validation_and_key_ownership(api):
    add_shloka(api)
    me = api.client.get("/me", headers=auth()).json()
    key = upload(api)
    assert key.startswith(f"rec/tmp/{me['id']}/")
    base = {"shloka_slug": "tat-savitur", "content_type": "audio/mp4", "size_bytes": 1000}
    for bad in (
        {**base, "content_type": "video/mp4"},
        {**base, "size_bytes": 3_000_000},
        {**base, "object_key": "rec/tmp/x"},
        {**base, "shloka_slug": "../etc"},
    ):
        assert (
            api.client.post("/recordings/upload-url", headers=auth(), json=bad).status_code == 422
        )
    add_shloka(api, "draft", verified=False, reference=False)
    r = api.client.post(
        "/recordings/upload-url", headers=auth(), json={**base, "shloka_slug": "draft"}
    )
    assert r.status_code == 404


def test_upload_url_rate_limit(api):
    add_shloka(api)
    for _ in range(3):
        upload(api)
    r = api.client.post(
        "/recordings/upload-url",
        headers=auth(),
        json={"shloka_slug": "tat-savitur", "content_type": "audio/mp4", "size_bytes": 10},
    )
    assert r.status_code == 429


def test_score_flow_without_consent_keeps_no_audio(api):
    add_shloka(api)
    key = upload(api)
    r = api.client.post(
        "/score-pronunciation",
        headers=auth(),
        json={"shloka_slug": "tat-savitur", "object_key": key},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overall"] == 70 and body["low_match"] is False
    assert body["words"][1]["issue_code"] == "aspiration_missing"
    assert ("recordings", key) not in api.storage.objects  # tmp deleted
    assert not any(k.startswith("rec/consented/") for _, k in api.storage.objects)
    row = api.sql("SELECT recording_r2_key, overall_score FROM attempts").one()
    assert row == (None, 70)
    assert api.sql("SELECT count(*) FROM attempt_word_scores").scalar() == 2
    sent = api.scorer.calls[0]
    assert sent["reference"]["key"].startswith("ref/") and sent["text_iast"] == "tat savitur"
    hist = api.client.get("/me/attempts", headers=auth()).json()
    assert [h["slug"] for h in hist] == ["tat-savitur"]


def test_score_flow_with_consent_keeps_a_copy(api):
    add_shloka(api)
    api.client.put(
        "/me/consent",
        headers=auth(),
        json={"recording_consent": True, "consent_version": "2026-10-v1"},
    )
    key = upload(api)
    r = api.client.post(
        "/score-pronunciation",
        headers=auth(),
        json={"shloka_slug": "tat-savitur", "object_key": key},
    )
    stored = api.sql("SELECT recording_r2_key FROM attempts").scalar()
    assert stored == f"rec/consented/{key.split('/')[2]}/{r.json()['attempt_id']}.m4a"
    assert ("recordings", stored) in api.storage.objects
    assert ("recordings", key) not in api.storage.objects


def test_cannot_score_someone_elses_recording(api):
    add_shloka(api)
    key = upload(api, headers=auth(sub="user_alice"))
    r = api.client.post(
        "/score-pronunciation",
        headers=auth(sub="user_bob"),
        json={"shloka_slug": "tat-savitur", "object_key": key},
    )
    assert r.status_code == 403
    r = api.client.post(
        "/score-pronunciation",
        headers=auth(),
        json={"shloka_slug": "tat-savitur", "object_key": "ref/x/y.m4a"},
    )
    assert r.status_code == 403


def test_oversized_upload_is_deleted(api):
    add_shloka(api)
    key = upload(api, size=1000)
    api.storage.put("recordings", key, 5_000_000)  # client ignored the limit
    r = api.client.post(
        "/score-pronunciation",
        headers=auth(),
        json={"shloka_slug": "tat-savitur", "object_key": key},
    )
    assert r.status_code == 413
    assert ("recordings", key) not in api.storage.objects


def test_scoring_limit_per_hour(connection):
    api = make_api(connection, scoring_per_hour=1, upload_urls_per_minute=10)
    add_shloka(api)
    body = lambda k: {"shloka_slug": "tat-savitur", "object_key": k}  # noqa: E731
    assert (
        api.client.post("/score-pronunciation", headers=auth(), json=body(upload(api))).status_code
        == 200
    )
    assert (
        api.client.post("/score-pronunciation", headers=auth(), json=body(upload(api))).status_code
        == 429
    )


def test_low_match_is_flagged(connection):
    api = make_api(connection)
    api.scorer._match = 0.3
    add_shloka(api)
    r = api.client.post(
        "/score-pronunciation",
        headers=auth(),
        json={"shloka_slug": "tat-savitur", "object_key": upload(api)},
    )
    assert r.json()["low_match"] is True and r.json()["message"]


def test_no_scoring_without_verified_reference(api):
    add_shloka(api, reference=False)
    r = api.client.post(
        "/score-pronunciation",
        headers=auth(),
        json={"shloka_slug": "tat-savitur", "object_key": upload(api)},
    )
    assert r.status_code == 404


def test_reference_audio_needs_login_and_returns_signed_url(api):
    add_shloka(api)
    assert api.client.get("/shlokas/tat-savitur/reference-audio").status_code == 401
    r = api.client.get("/shlokas/tat-savitur/reference-audio", headers=auth()).json()
    assert r["url"].startswith("memory://reference/ref/") and r["expires_in"] <= 900
    assert r["word_marks"] == []


def test_unverified_shloka_scoring_blocked_even_with_reference(api):
    sid = add_shloka(api, verified=False)
    assert sid
    r = api.client.post(
        "/score-pronunciation",
        headers=auth(),
        json={"shloka_slug": "tat-savitur", "object_key": f"rec/tmp/{'0' * 36}/{'0' * 32}.m4a"},
    )
    assert r.status_code in (403, 404)
    assert api.sql("SELECT count(*) FROM attempts").scalar() == 0
