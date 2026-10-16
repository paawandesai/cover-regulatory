"""API tests against the local database. Skipped when it is not reachable."""

import base64

import pytest
from fastapi.testclient import TestClient

from app.api import ratelimit
from app.api.auth import hash_password
from app.config import get_settings

try:
    from app.db.connection import connect

    with connect() as _c:
        _c.execute("SELECT 1 FROM rule_fragment LIMIT 1")
except Exception:  # noqa: BLE001
    pytest.skip("database not reachable", allow_module_level=True)

from app.api.main import app

PASSWORD = "correct horse battery staple"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "reviewer")
    monkeypatch.setenv("ADMIN_PASSWORD_SCRYPT", hash_password(PASSWORD))
    get_settings.cache_clear()
    ratelimit.reset()
    yield TestClient(app)
    ratelimit.reset()
    get_settings.cache_clear()


def auth(user="reviewer", pw=PASSWORD):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


def test_health_has_no_secrets_and_noindex(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.headers["X-Robots-Tag"].startswith("noindex")
    body = r.text
    assert "scrypt$" not in body and "sk-ant" not in body
    assert isinstance(r.json()["llm_key_configured"], bool)


def test_admin_requires_credentials(client):
    assert client.get("/api/admin/fragments").status_code == 401
    assert client.get("/api/admin/fragments", headers=auth(pw="wrong password")).status_code == 401
    assert client.get("/api/admin/fragments", headers=auth()).status_code == 200


def test_admin_disabled_without_config(monkeypatch):
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_SCRYPT", raising=False)
    get_settings.cache_clear()
    try:
        r = TestClient(app).get("/api/admin/fragments", headers=auth())
        assert r.status_code == 503
    finally:
        get_settings.cache_clear()


def test_invalid_fragment_cannot_be_approved(client):
    with connect() as conn:
        row = conn.execute("SELECT id FROM rule_fragment WHERE status = 'invalid' LIMIT 1").fetchone()
    if row is None:
        pytest.skip("no invalid fragment to test with")
    r = client.post(f"/api/admin/fragments/{row['id']}", json={"decision": "approved"}, headers=auth())
    assert r.status_code == 409


def test_chunk_lookup(client):
    r = client.get("/api/chunks/does-not-exist")
    assert r.status_code == 404


def test_nearby_parcels_return_geometry_only(client):
    r = client.get("/api/parcels/2121005008/nearby")
    assert r.status_code == 200
    feats = r.json()["features"]
    assert feats and all(set(f["properties"]) == {"apn"} for f in feats)
    assert client.get("/api/parcels/not-an-apn/nearby").status_code == 422


def test_assessment_returns_lot_outline_when_yards_are_withheld(client):
    # Lot width and depth cannot be measured on this outline, so no yards: the lot is still drawn, with no envelope.
    g = client.get("/api/assess", params={"q": "4411004005"}).json()["geometry"]
    assert g["lot"]["type"] in ("Polygon", "MultiPolygon")
    assert g["envelope"] is None and g["yards_ft"] is None


def test_invite_gate(monkeypatch, client):
    monkeypatch.setenv("DEMO_INVITE_CODE", "blue heron")
    get_settings.cache_clear()
    assert client.get("/api/health").status_code == 200
    r = client.get("/api/assess", params={"q": "2121005008"})
    assert r.status_code == 401 and r.json()["detail"] == "invite_required"
    assert r.headers["X-Robots-Tag"].startswith("noindex")
    assert client.post("/api/invite", json={"code": "wrong"}).status_code == 403
    r = client.post("/api/invite", json={"code": "blue heron"})
    assert r.status_code == 200
    assert "blue heron" not in r.headers["set-cookie"]
    assert client.get("/api/invite").json() == {"required": True, "ok": True}
    assert client.get("/api/assess", params={"q": "2121005008"}).status_code == 200


def test_no_gate_without_code(client, monkeypatch):
    assert client.get("/api/invite").json() == {"required": False, "ok": True}
    # docker compose passes an unset variable as "", which must also mean no gate.
    monkeypatch.setenv("DEMO_INVITE_CODE", "")
    get_settings.cache_clear()
    assert client.get("/api/invite").json() == {"required": False, "ok": True}
    assert client.get("/api/assess", params={"q": "2121005008"}).status_code == 200


def test_verification_is_shown_but_never_changes_status(client, tmp_path):
    import json

    from app.extract.verification import load

    with connect() as conn:
        f = conn.execute("SELECT id, chunk_id, parameter, status FROM rule_fragment ORDER BY id LIMIT 1").fetchone()
        before = conn.execute("SELECT * FROM fragment_verification WHERE fragment_id = %s", (f["id"],)).fetchone()
    data = {
        "checked_on": "2026-10-15",
        "candidates": [
            {
                **{k: f[k] for k in ("chunk_id", "parameter")},
                "fragment_id": f["id"],
                "recommendation": "reject",
                "note": "test note",
                "checks": {"web": "outdated or wrong"},
            },
            {
                "fragment_id": f["id"],
                "chunk_id": "elsewhere",
                "parameter": "x",
                "recommendation": "approve",
                "note": None,
                "checks": {},
            },
        ],
    }
    path = tmp_path / "v.json"
    path.write_text(json.dumps(data))
    try:
        assert load(path) == (1, 1)
        rows = client.get(f"/api/admin/fragments?status={f['status']}", headers=auth()).json()
        row = next(r for r in rows if r["id"] == f["id"])
        assert row["check_recommendation"] == "reject" and row["check_note"] == "test note"
        assert row["status"] == f["status"]
    finally:
        with connect() as conn:
            conn.execute("DELETE FROM fragment_verification WHERE fragment_id = %s", (f["id"],))
            if before:
                conn.execute(
                    "INSERT INTO fragment_verification VALUES (%s, %s, %s, %s, %s)",
                    (
                        before["fragment_id"],
                        before["checked_on"],
                        before["recommendation"],
                        before["note"],
                        json.dumps(before["checks"]),
                    ),
                )
            conn.commit()


def test_ai_review_only_decides_pending_fragments(tmp_path):
    import json

    from app.extract.apply_review import apply

    with connect() as conn:
        f = conn.execute(
            "SELECT id, chunk_id, parameter FROM rule_fragment WHERE status <> 'pending' ORDER BY id LIMIT 1"
        ).fetchone()
    if f is None:
        pytest.skip("no decided fragment to test with")
    c = {"fragment_id": f["id"], "chunk_id": f["chunk_id"], "parameter": f["parameter"], "recommendation": "reject"}
    path = tmp_path / "v.json"
    path.write_text(json.dumps({"checked_on": "2026-10-15", "candidates": [c]}))
    assert apply(path, "test") == {"approved": 0, "rejected": 0, "skipped": 1}


def test_existing_buildings_are_returned_with_attribution(client):
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM building_footprint_odbl LIMIT 1").fetchone():
            pytest.skip("footprints not loaded")
    r = client.get("/api/assess?q=2104024009").json()
    item = next(i for i in r["items"] if i["id"] == "existing_footprint")
    assert item["value"].startswith("1 building") and item["label"] == "approximate"
    assert "ODbL" in item["source"]["attribution"]
    assert len(r["geometry"]["buildings"]) == 1
    vacant = client.get("/api/assess?q=2121005008").json()
    assert next(i for i in vacant["items"] if i["id"] == "existing_footprint")["value"] == "None found"


def test_address_lookup_finds_the_parcel(client):
    # The address is read from the loaded parcel roll, so no street address is committed to the repo.
    with connect() as conn:
        row = conn.execute(
            "SELECT situs_house_no, situs_direction, situs_street FROM parcel WHERE apn = '2104024009'"
        ).fetchone()
    if not row or not row["situs_house_no"]:
        pytest.skip("situs not loaded")
    address = " ".join(str(v) for v in (row["situs_house_no"], row["situs_direction"], row["situs_street"]) if v)
    r = client.get("/api/assess", params={"q": address})
    assert r.status_code == 200
    assert r.json()["parcel"]["apn"] == "2104024009"


def test_unknown_apn_is_not_found(client):
    assert client.get("/api/assess?q=9999999999").status_code == 404


def test_project_inputs_change_checks_and_side_yard(client):
    plain = client.get("/api/assess?q=2121005008").json()
    assert plain["project"] is None and plain["summary"]["answer"]
    r = client.get(
        "/api/assess",
        params={
            "q": "2121005008",
            "height_ft": 24,
            "floor_area_sqft": 4000,
            "second_unit": "detached",
            "second_unit_sqft": 700,
        },
    ).json()
    checks = {c["id"]: c["status"] for c in r["project"]["checks"]}
    assert checks == {"height": "fits", "side_yard": "fits", "floor_area": "exceeds", "adu_detached": "fits"}
    side = next(i for i in r["items"] if i["id"] == "side_yard")
    assert side["value"] == 6.0  # 5 ft + 1 ft for 24 ft (one 10 ft increment above 18 ft)
    assert r["geometry"]["yards_ft"]["side"] == 6.0
    assert client.get("/api/assess", params={"q": "2121005008", "second_unit": "garage"}).status_code == 422


def test_feedback_can_be_marked_reviewed_without_touching_rules(client):
    before = client.get("/api/admin/fragments?status=approved", headers=auth()).json()
    fid = client.post("/api/feedback", json={"apn": "2121005008", "item_id": "side_yard", "kind": "other"}).json()["id"]
    assert any(f["id"] == fid for f in client.get("/api/admin/feedback", headers=auth()).json())
    assert client.post(f"/api/admin/feedback/{fid}", json={"status": "reviewed"}).status_code == 401
    r = client.post(f"/api/admin/feedback/{fid}", json={"status": "reviewed"}, headers=auth())
    assert r.json()["status"] == "reviewed"
    done = client.get("/api/admin/feedback?status=reviewed", headers=auth()).json()
    assert next(f for f in done if f["id"] == fid)["reviewed_by"] == "reviewer"
    assert client.get("/api/admin/fragments?status=approved", headers=auth()).json() == before
    with connect() as conn:
        conn.execute("DELETE FROM feedback WHERE id = %s", (fid,))
        conn.commit()


def test_wrong_passwords_are_rate_limited(client):
    for _ in range(ratelimit.LIMITS["auth_fail"][0]):
        assert client.get("/api/admin/feedback", headers=auth(pw="wrong")).status_code == 401
    assert client.get("/api/admin/feedback", headers=auth(pw="wrong")).status_code == 429
    # Even the right password waits until the window passes, so guessing can't continue.
    assert client.get("/api/admin/feedback", headers=auth()).status_code == 429
