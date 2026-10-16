"""Golden cases against the local database (skipped when it is not reachable)."""

from pathlib import Path

import pytest
import yaml

try:
    from app.db.connection import connect

    with connect() as _c:
        _c.execute("SELECT 1 FROM rule_fragment LIMIT 1")
except Exception:  # noqa: BLE001
    pytest.skip("database not reachable", allow_module_level=True)

from app.engine.assess import assess

CASES = yaml.safe_load((Path(__file__).with_name("cases.yaml")).read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["apn"] for c in CASES])
def test_golden(case):
    r = assess(case["apn"])
    assert r["status"] == case["status"]
    items = {i["id"]: i for i in r["items"]}
    for key, want in (case.get("expect") or {}).items():
        got = items[key]
        assert got["value"] == want, f"{key}: got {got['value']}, expected {want}"
        if want is not None:
            # A number is only shown with cited text behind it, and never as "verified".
            assert got["label"] in ("derived", "interpretive"), key
            assert got["citations"], key
    for key, want in (case.get("labels") or {}).items():
        assert items[key]["label"] == want, f"{key}: label {items[key]['label']}, expected {want}"
    flags = {i["id"] for i in r["items"] if i["family"] == "flag"}
    assert set(case.get("flags_include", [])) <= flags
    assert not (set(case.get("flags_exclude", [])) & flags)
    if case["status"] != "ok":
        assert r["items"] == []
    assert any("not for legal" in d or "not be suitable for legal" in d for d in r["disclaimers"])
    assert r["ai_disclosure"]


def test_single_story_district(monkeypatch):
    """No loaded parcel is in Height District 1-SS, so one R1 parcel is resolved as if it were."""
    import dataclasses

    from app.engine import assess as A

    real = A.resolve

    def as_ss(q):
        ctx = real(q)
        ctx.zone = dataclasses.replace(ctx.zone, height_district="1SS")
        return ctx

    monkeypatch.setattr(A, "resolve", as_ss)
    items = {i["id"]: i for i in assess("2228004010")["items"]}
    h = items["max_height"]
    assert h["value"] == 18 and h["label"] == "derived"
    assert "one story" in h["explanation"]
    assert any(c["section_id"] == "LAMC 12.21.1 A.1" for c in h["citations"])
    assert items["side_yard"]["value"] == 5  # no extra side yard at 18 ft
