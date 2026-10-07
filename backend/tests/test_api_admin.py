"""Admin/advisor routes: content editing, verification, recordings, labels, audit."""

from .api_helpers import add_shloka, auth

ADMIN, ADVISOR = auth("admin"), auth("advisor")


def test_staff_see_drafts_and_full_detail(api):
    add_shloka(api, "draft", verified=False, reference=False)
    listed = api.client.get("/admin/shlokas", headers=ADMIN).json()
    assert [(s["slug"], s["verified"]) for s in listed] == [("draft", False)]
    detail = api.client.get("/admin/shlokas/draft", headers=ADVISOR).json()
    assert detail["source"]["license"] == "CC0-1.0" and len(detail["words"]) == 2
    assert api.client.get("/admin/shlokas/nope", headers=ADMIN).status_code == 404


def test_edit_verify_and_reset_cycle(api):
    add_shloka(api, "draft", verified=False, reference=False)
    r = api.client.patch("/admin/shlokas/draft", headers=ADMIN, json={"translation": "That..."})
    assert r.status_code == 200 and r.json()["translation"] == "That..."
    assert api.client.post("/admin/shlokas/draft/verify", headers=ADMIN, json={}).status_code == 403
    r = api.client.post("/admin/shlokas/draft/verify", headers=ADVISOR, json={"notes": "ok"})
    assert r.json()["verified"] is True and r.json()["verified_by"] == "user_advisor"
    assert [s["slug"] for s in api.client.get("/shlokas").json()] == ["draft"]
    r = api.client.patch("/admin/shlokas/draft", headers=ADMIN, json={"title": "Renamed"})
    assert r.json()["verified"] is False
    assert api.client.get("/shlokas").json() == []
    actions = [a["action"] for a in api.client.get("/admin/audit", headers=ADMIN).json()]
    assert actions[:3] == ["update", "verify", "update"]


def test_clients_cannot_set_verified_or_unknown_fields(api):
    add_shloka(api, "draft", verified=False, reference=False)
    for body in ({"verified": True}, {"verified_by": "me"}, {"title": "x" * 201}):
        assert (
            api.client.patch("/admin/shlokas/draft", headers=ADVISOR, json=body).status_code == 422
        )


def test_analysis_edit_and_verify(api):
    sid = add_shloka(api, "draft", verified=False, reference=False)
    wid = api.sql(
        "SELECT id FROM shloka_words WHERE shloka_id = :s AND position = 0", s=sid
    ).scalar()
    aid = api.sql(
        "INSERT INTO word_analyses (shloka_word_id, position, pada_iast) "
        "VALUES (:w, 0, 'tat') RETURNING id",
        w=wid,
    ).scalar()
    r = api.client.patch(
        f"/admin/word-analyses/{aid}",
        headers=ADMIN,
        json={"meaning": "that", "morphology": {"chosen": {"case": "nominative"}}},
    )
    assert r.status_code == 200
    assert api.client.post(f"/admin/word-analyses/{aid}/verify", headers=ADMIN).status_code == 403
    assert api.client.post(f"/admin/word-analyses/{aid}/verify", headers=ADVISOR).json()["verified"]
    bad = api.client.patch(f"/admin/word-analyses/{aid}", headers=ADMIN, json={"morphology": "x"})
    assert bad.status_code == 422


def test_recording_lifecycle(api):
    add_shloka(api, "draft", verified=False, reference=False)
    up = api.client.post(
        "/admin/audio/upload-url",
        headers=ADMIN,
        json={"shloka_slug": "draft", "kind": "reference", "content_type": "audio/mp4"},
    ).json()
    key = up["r2_key"]
    assert key.startswith("ref/draft/")
    meta = {
        "shloka_slug": "draft",
        "kind": "reference",
        "r2_key": key,
        "reciter": "Advisor A",
        "license": "owned",
        "attribution": "Vedic Voice",
    }
    assert (
        api.client.post("/admin/audio", headers=ADMIN, json=meta).status_code == 409
    )  # not uploaded
    api.storage.put("reference", key, 80_000)
    asset = api.client.post("/admin/audio", headers=ADMIN, json=meta).json()
    aid = asset["id"]
    assert api.client.post(f"/admin/audio/{aid}/activate", headers=ADMIN).status_code == 422
    assert api.client.post(f"/admin/audio/{aid}/verify", headers=ADMIN).status_code == 403
    api.client.post(f"/admin/audio/{aid}/verify", headers=ADVISOR)
    act = api.client.post(f"/admin/audio/{aid}/activate", headers=ADMIN).json()
    assert act["is_active_reference"] is True
    play = api.client.get(f"/admin/audio/{aid}/play-url", headers=ADMIN).json()
    assert play["url"].startswith("memory://reference/ref/draft/")
    assert len(api.client.get("/admin/audio?shloka=draft", headers=ADMIN).json()) == 1


def test_test_recordings_need_license(api):
    add_shloka(api, "draft", verified=False, reference=False)
    key = api.client.post(
        "/admin/audio/upload-url",
        headers=ADMIN,
        json={"shloka_slug": "draft", "kind": "test", "content_type": "audio/ogg"},
    ).json()["r2_key"]
    api.storage.put("reference", key, 1000)
    body = {"shloka_slug": "draft", "kind": "test", "r2_key": key}
    assert api.client.post("/admin/audio", headers=ADMIN, json=body).status_code == 422
    ok = {**body, "license": "CC-BY-4.0", "attribution": "IISc Su-śrotā"}
    assert api.client.post("/admin/audio", headers=ADMIN, json=ok).status_code == 201
    mismatch = {**ok, "kind": "reference"}
    assert api.client.post("/admin/audio", headers=ADMIN, json=mismatch).status_code == 422


def test_word_labels_upsert(api):
    sid = add_shloka(api)
    aid = api.sql("SELECT id FROM audio_assets WHERE shloka_id = :s", s=sid).scalar()
    wid = api.sql(
        "SELECT id FROM shloka_words WHERE shloka_id = :s AND position = 1", s=sid
    ).scalar()
    body = {
        "audio_asset_id": str(aid),
        "shloka_word_id": str(wid),
        "ok": False,
        "issue_code": "aspiration_missing",
    }
    assert api.client.put("/admin/word-labels", headers=ADVISOR, json=body).status_code == 204
    assert (
        api.client.put(
            "/admin/word-labels", headers=ADVISOR, json={**body, "ok": True, "issue_code": None}
        ).status_code
        == 204
    )
    assert api.sql("SELECT count(*), bool_and(ok) FROM word_labels").one() == (1, True)
    assert api.client.put("/admin/word-labels", headers=auth(), json=body).status_code == 403
