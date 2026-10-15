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
    flags = {i["id"] for i in r["items"] if i["family"] == "flag"}
    assert set(case.get("flags_include", [])) <= flags
    assert not (set(case.get("flags_exclude", [])) & flags)
    if case["status"] != "ok":
        assert r["items"] == []
    assert any("not for legal" in d or "not be suitable for legal" in d for d in r["disclaimers"])
    assert r["ai_disclosure"]
