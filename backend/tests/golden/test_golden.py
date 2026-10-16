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


@pytest.mark.parametrize(
    "zone,rfa,height,coverage",
    [
        # 8,100 sq ft lot, 135 ft deep. Table 12.08 C.5.(c), 8,001 to 9,000 sq ft row: R1F3 .39 and 44%; front mass 28 ft.
        ("R1F3-1", 3159, 28.0, 3564),
        # Table 12.08 C.5.(d): R1R2 .49 and 44%; rear mass 30 ft (the lot is over 90 ft deep).
        ("R1R2-1", 3969, 30.0, 3564),
        # Table 12.08 C.5.(b): R1V4 .34 and 44%; 20 ft.
        ("R1V4-1", 2754, 20.0, 3564),
    ],
)
def test_variation_zones(monkeypatch, zone, rfa, height, coverage):
    """No loaded parcel carries these variations with a height district, so a vacant 8,100 sq ft R1 lot is
    resolved as if it did. Expected values read from the tables by hand."""
    from app.engine import assess as A
    from app.parcel.zone import parse_zone

    real = A.resolve

    def as_zone(q):
        ctx = real(q)
        ctx.zone = parse_zone(zone)
        return ctx

    monkeypatch.setattr(A, "resolve", as_zone)
    items = {i["id"]: i for i in assess("2121005008")["items"]}
    assert items["max_rfa"]["value"] == rfa and items["max_rfa"]["label"] == "derived"
    assert items["max_height"]["value"] == height and items["max_height"]["label"] == "derived"
    assert items["max_lot_coverage"]["value"] == coverage
    assert any(c["section_id"].startswith("LAMC 12.08 C.5(") for c in items["max_rfa"]["citations"])


def test_coastal_zone_flat_lot():
    """4412-014-018: R1-1 in the Coastal Zone, off the Hillside Area, about 50 x 150 ft. LAMC 12.21.1: 45 ft;
    12.21.1 A.1: three times the buildable area, by hand (50 - 2 x 5) x (150 - 20 - 15) = 4,600 sq ft, so about
    13,800 sq ft (the outline is not an exact rectangle, hence the tolerance)."""
    r = assess("4412014018")
    items = {i["id"]: i for i in r["items"]}
    assert items["max_height"]["value"] == 45 and items["max_height"]["label"] == "derived"
    assert abs(items["max_rfa"]["value"] - 13800) <= 0.01 * 13800
    assert items["max_rfa"]["label"] == "interpretive"
    assert "coastal" in {i["id"] for i in r["items"] if i["family"] == "flag"}


def test_2025_fire_map_flag(monkeypatch):
    """No City lot in the loaded areas changes class on CAL FIRE's 2025 map, so one lot is resolved as if it did."""
    from app.engine import assess as A

    real = A.resolve

    def newly_very_high(q):
        ctx = real(q)
        ctx.overlays = [o for o in ctx.overlays if o["kind"] != "vhfhsz"] + [
            {"kind": "vhfhsz_2025", "name": "Very High"}
        ]
        return ctx

    monkeypatch.setattr(A, "resolve", newly_very_high)
    flags = {i["id"]: i for i in assess("2228004010")["items"] if i["family"] == "flag"}
    assert "vhfhsz_2025" in flags and "vhfhsz" not in flags
    assert flags["vhfhsz_2025"]["citations"]


def test_fire_rebuild_coastal_lot():
    """4412-014-018: built-up R1-1 lot in the Coastal Zone inside the Palisades Fire perimeter. EO 1 B.3: 110% of the
    building outlines on the lot (about 2,795 sq ft); EO 8 A.1: the flat-land Height District 1 limit, 33 ft."""
    items = {i["id"]: i for i in assess("4412014018")["items"]}
    fp = items["eo1_footprint"]
    assert abs(fp["value"] - 1.1 * 2795) <= 2 and fp["label"] == "approximate"
    assert any(c["section_id"] == "EO 1 B.3" for c in fp["citations"])
    assert items["eo8_height"]["value"] == 33 and items["eo8_height"]["label"] == "derived"
    assert items["sb9_two_unit"]["value"] is False  # EO 9: Very High fire zone inside the Palisades Fire area


def test_sb9_lot_too_small_to_split():
    """66411.7(a)(2): both new lots at least 1,200 sq ft, so a 2,000 sq ft lot cannot be split."""
    from app.engine.orders import sb9_items
    from app.parcel.resolve import resolve

    with connect() as conn:
        items = {i.id: i for i in sb9_items(conn, resolve("2121005008"), 2000, set())}
    assert items["sb9_lot_split"].value is False and items["sb9_lot_split"].label == "derived"
    assert items["sb9_two_unit"].value == 2
