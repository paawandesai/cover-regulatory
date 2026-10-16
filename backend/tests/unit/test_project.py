"""Project inputs and the summary, against hand-built items (no database needed)."""

from types import SimpleNamespace as NS

from app.engine.project import ProjectInputs, check_project, summarize


def item(id, value, label="derived", title=None):
    return NS(id=id, value=value, label=label, title=title or id)


ITEMS = [
    item("front_yard", 20.0),
    item("side_yard", 7.0),
    item("rear_yard", 15.0),
    item("max_height", 33.0),
    item("max_rfa", 3645),
    item("guest_house", False),
    item("adu_state_detached", 800.0),
    item("adu_local_detached", 1200.0),
    item("adu_attached", 850),
    item("jadu", 500.0),
]
CTX = NS(overlays=[])


def checks(**kw):
    return {c["id"]: c for c in check_project(ITEMS, ProjectInputs(**kw))["checks"]}


def test_empty_inputs():
    assert ProjectInputs().empty


def test_height_and_floor_area():
    c = checks(height_ft=36, floor_area_sqft=3000)
    assert c["height"]["status"] == "exceeds"
    assert c["floor_area"]["status"] == "fits"


def test_detached_adu_picks_the_path_by_size():
    assert checks(second_unit="detached", second_unit_sqft=750)["adu_detached"]["based_on"] == "adu_state_detached"
    c = checks(second_unit="detached", second_unit_sqft=1000)["adu_detached"]
    assert (c["based_on"], c["status"]) == ("adu_local_detached", "fits")
    assert checks(second_unit="detached", second_unit_sqft=1300)["adu_detached"]["status"] == "exceeds"


def test_attached_adu_floor_rises_with_bedrooms():
    assert checks(second_unit="attached", second_unit_sqft=950)["adu_attached"]["status"] == "exceeds"
    c = checks(second_unit="attached", second_unit_sqft=950, second_unit_bedrooms=2)["adu_attached"]
    assert c["status"] == "fits"


def test_guest_house_not_allowed_on_small_lot():
    assert checks(second_unit="guest_house")["guest_house"]["status"] == "exceeds"


def test_interpretive_basis_needs_confirmation():
    items = [item("max_height", 33.0, label="interpretive")]
    c = check_project(items, ProjectInputs(height_ft=30))["checks"][0]
    assert c["status"] == "confirm"


def test_withheld_limit_is_not_determined():
    items = [item("max_rfa", None, label="withheld")]
    c = check_project(items, ProjectInputs(floor_area_sqft=2000))["checks"][0]
    assert c["status"] == "not_determined"


def test_summary_counts_and_paths():
    s = summarize(ITEMS, CTX)
    assert "3,645 sq ft and 33 ft" in s["answer"]
    assert s["confidence"].startswith("Every rule value")
    assert {p["id"] for p in s["paths"]} == {"adu_path", "guest_or_adu"}
    fire = summarize(ITEMS, NS(overlays=[{"kind": "fire_perimeter_2025"}]))
    assert "rebuild_or_standard" in {p["id"] for p in fire["paths"]}


EX = {
    "double_ceiling_ft": 14.0,
    "parking_max_sqft": 400.0,
    "parking_fallback_sqft": 200.0,
    "parking_front_ft": 55.0,
    "parking_through_ft": 40.0,
    "accessory_each_sqft": 200.0,
    "accessory_total_sqft": 400.0,
}


def test_floor_area_exemptions():
    p = ProjectInputs(floor_area_sqft=3900, covered_parking_sqft=420, parking_in_rear=True, accessory_sqft=150)
    c = {x["id"]: x for x in check_project(ITEMS, p, EX)["checks"]}
    # 3,900 - 400 parking (rear, capped) - 150 shed = 3,350 <= 3,645
    assert c["floor_area"]["status"] == "fits" and "3,350" in c["floor_area"]["title"]


def test_parking_near_front_and_tall_ceilings():
    p = ProjectInputs(floor_area_sqft=3500, covered_parking_sqft=400, parking_in_rear=False, tall_ceiling_sqft=200)
    c = {x["id"]: x for x in check_project(ITEMS, p, EX)["checks"]}
    # 3,500 + 200 - 200 = 3,500 <= 3,645; without the reviewed numbers nothing is adjusted
    assert "3,500" in c["floor_area"]["title"] and c["floor_area"]["status"] == "fits"
    assert check_project(ITEMS, p)["checks"][0]["title"] == "Floor area 3,500 sq ft"


def test_plane_break():
    assert checks(side_wall_ft=50, height_ft=26)["plane_break"]["status"] == "confirm"
    assert checks(side_wall_ft=40)["plane_break"]["status"] == "fits"
