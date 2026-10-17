"""Unincorporated Los Angeles County, Zone R-1 (Title 22): the second jurisdiction.

Read from a copy of Title 22 Volume I supplied by the project owner. The copy does not state its edition (it uses the
2019 numbering and still calls ADUs "second units"), so every value here is labelled Interpretation, even where the
fragment behind it was approved. ADUs follow state law, which applies to counties as to cities.
"""

from app.engine import rules as R
from app.engine.item import Item, chunk_citation, rule_item
from app.engine.orders import sb9_items

EDITION = (
    " Read from a copy of Title 22 whose edition is not stated (2019 numbering, before the County's 2020 ADU "
    "amendments); later amendments may change this."
)


def _interpretive(items: list[Item]) -> list[Item]:
    for i in items:
        if i.label == "derived":
            i.label, i.coverage = "interpretive", 1.0
            i.explanation = (i.explanation or "") + EDITION
    return items


def envelope_items(
    conn, ctx, width, depth, lot_area, corner: str | None = None
) -> tuple[list[Item], float | None, float | None, float | None]:
    """corner is None for an interior lot, "corner" or "reversed" (a reversed corner lot) as read from the map."""
    cz = ctx.county_zone
    yards = R.load("COUNTY_R1_YARDS", conn)
    narrow = R.load("COUNTY_NARROW_LOT", conn)
    shallow = R.load("COUNTY_SHALLOW_LOT", conn)
    items: list[Item] = []

    front = yards.value("front")
    items.append(
        rule_item(
            "front_yard",
            "county_r1_envelope",
            "Front yard (minimum)",
            yards,
            front,
            "ft",
            f"{front:g} ft for Zone R-1 (Table 22.18.040-A). Where other lots on the block have buildings, a front yard "
            "as deep as the average of the two neighboring lots is allowed instead (22.110.080 B.1); not computed."
            if front is not None
            else None,
        )
    )

    base_side = yards.value("side")
    side, side_why, side_rules = base_side, None, yards
    if base_side is not None:
        side_why = f"{base_side:g} ft on each interior side for Zone R-1 (Table 22.18.040-A)."
        n_pct, n_min = narrow.value("pct"), narrow.value("min_ft")
        if width and width < 50 and n_pct and n_min is not None:
            side = round(max(width * n_pct / 100, n_min), 1)
            side_rules = narrow
            side_why = (
                f"This lot is about {width:.0f} ft wide, under 50 ft, so its interior side yards may be {n_pct:g}% of the "
                f"average width but not less than {n_min:g} ft: {side:g} ft (22.110.080 C.2), instead of the zone's "
                f"{base_side:g} ft. It is an allowance; {base_side:g} ft also complies."
            )
        if corner is None:
            side_why += " This lot was read as an interior lot, so there is no street side yard."
    side_item = rule_item(
        "side_yard", "county_r1_envelope", "Side yards (minimum, each)", side_rules, side, "ft", side_why
    )
    if side_rules is narrow:
        side_item.citations = yards.citations() + side_item.citations
    items.append(side_item)
    if corner is not None:
        items.append(_street_side(conn, yards, corner))

    base_rear = yards.value("rear")
    rear, rear_why, rear_rules = base_rear, None, yards
    if base_rear is not None:
        rear_why = f"{base_rear:g} ft for Zone R-1 (Table 22.18.040-A)."
        s_pct, s_min = shallow.value("pct"), shallow.value("min_ft")
        if depth and depth < 75 and s_pct and s_min is not None:
            rear = round(max(depth * s_pct / 100, s_min), 1)
            rear_rules = shallow
            rear_why = (
                f"This lot is about {depth:.0f} ft deep, under 75 ft, so its rear yard may be {s_pct:g}% of the average "
                f"depth but not less than {s_min:g} ft: {rear:g} ft (22.110.080 D), instead of the zone's "
                f"{base_rear:g} ft. It is an allowance; {base_rear:g} ft also complies."
            )
    rear_item = rule_item("rear_yard", "county_r1_envelope", "Rear yard (minimum)", rear_rules, rear, "ft", rear_why)
    if rear_rules is shallow:
        rear_item.citations = yards.citations() + rear_item.citations
    items.append(rear_item)

    h = R.load("COUNTY_R1_HEIGHT", conn)
    hmax = h.value("max_ft")
    items.append(
        rule_item(
            "max_height",
            "county_r1_envelope",
            "Maximum height",
            h,
            hmax,
            "ft",
            f"No building or structure on an R-1 lot may be more than {hmax:g} ft above grade (22.18.040 B.1). "
            "Title 22 sets no floor area ratio for Zone R-1 in the sections loaded here; a Community Standards District "
            "can add one."
            if hmax is not None
            else None,
        )
    )

    la = R.load("COUNTY_LOT_AREA", conn)
    required = (
        cz.lot_area_sqft if cz and cz.lot_area_sqft else (5000 if la.found["default"].status != "missing" else None)
    )
    if required is not None:
        src = (
            f"the {cz.lot_area_sqft:,} after the zone symbol is the required net lot area in square feet"
            if cz and cz.lot_area_sqft
            else "with no number after the zone symbol, Zone R-1 takes the required area of Zone R-1-5000"
        )
        meets = lot_area >= required if lot_area else None
        why = (
            f"In {cz.raw if cz else 'R-1'}, {src} (22.110.130 A.3, A.4). "
            + (
                f"This lot is {lot_area:,.0f} sq ft (Assessor), "
                + ("so it meets that." if meets else "below that, so it is a substandard lot (22.110.150).")
                if lot_area
                else ""
            )
            + " A lot created before the area requirement by deed or recorded map keeps its own area as the required "
            "area (A.1, A.2), and a flag lot's access strip does not count (A.3.b)."
        )
    else:
        why = None
    items.append(rule_item("lot_minimum", "county_r1_envelope", "Required lot area", la, required, "sqft", why))
    return _interpretive(items), front, side, rear


def _street_side(conn, yards, corner: str) -> Item:
    """The corner side yard, on the street side of a corner lot (Table 22.18.040-A)."""
    if corner == "reversed":
        rc = R.load("COUNTY_REVERSED_CORNER", conn)
        ft = rc.value("side_ft")
        item = rule_item(
            "street_side_yard",
            "county_r1_envelope",
            "Street side yard (reversed corner lot)",
            rc,
            ft,
            "ft",
            f"The lot behind this one fronts its side street, so this reads as a reversed corner lot, whose street side "
            f"yard is {ft:g} ft (Table 22.18.040-A, Corner Side, Reversed Corner Lot column). Where the front yard of "
            "the key lot behind it is under 10 ft, this side yard may match it but not be less than 5 ft "
            "(22.110.080 C.1). Which lots are reversed corner lots was read from the parcel map; confirm it."
            if ft is not None
            else None,
        )
        item.citations = yards.citations() + item.citations
        return item
    ft = yards.value("corner_side")
    return rule_item(
        "street_side_yard",
        "county_r1_envelope",
        "Street side yard (corner lot)",
        yards,
        ft,
        "ft",
        f"This lot was read as a corner lot. Its street side yard is {ft:g} ft (Table 22.18.040-A, Corner Side column), "
        "the same as the interior side. If the lot behind it fronts the side street, it is a reversed corner lot and "
        "needs more; the parcel map did not show that here."
        if ft is not None
        else None,
    )


def overlay_notes(conn, ctx, items: list[Item]) -> list[Item]:
    """Districts that can change the R-1 values. Each turns the envelope into an interpretation and gets a flag."""
    kinds = {o["kind"]: o for o in ctx.overlays}
    out: list[Item] = []
    if "county_csd" in kinds:
        name = kinds["county_csd"]["name"] or "a Community Standards District"
        out.append(
            Item(
                "flag_county_csd",
                "flag",
                "Community Standards District",
                name,
                None,
                "flag",
                rule_id="FLAG_COUNTY_CSD",
                explanation=f"This lot is in the {name}. Its standards (Title 22 Volume II, not loaded) supersede the "
                "zone's where they differ (22.06.040), so the values above may not apply.",
                citations=chunk_citation(conn, "LACC 22.06.040", "supersede"),
            )
        )
    if "county_setback_district" in kinds:
        out.append(
            Item(
                "flag_county_setback_district",
                "flag",
                "Setback District",
                kinds["county_setback_district"]["name"],
                None,
                "flag",
                rule_id="FLAG_COUNTY_SETBACK",
                explanation="A Setback District sets its own yards on this street; not loaded, so the yards above may "
                "not apply.",
            )
        )
    if "county_hma" in kinds:
        out.append(
            Item(
                "flag_county_hma",
                "flag",
                "Hillside Management Area",
                "Part of the lot has a natural slope of 25% or more",
                None,
                "flag",
                rule_id="FLAG_COUNTY_HMA",
                explanation="Building in a Hillside Management Area needs a Conditional Use Permit unless an exemption "
                "applies; one single-family home, additions that add no family, and accessory buildings are exempt "
                "(22.102.020, 22.102.030). The urban-area density threshold is not checked here.",
                citations=chunk_citation(conn, "LACC 22.102.020 B", "Hillside")
                + chunk_citation(conn, "LACC 22.102.030 C", "Individual single-family"),
            )
        )
    if {"county_csd", "county_setback_district"} & set(kinds):
        for i in items:
            if i.family == "county_r1_envelope" and i.value is not None:
                i.explanation = (i.explanation or "") + " A district on this lot may change it (see the flags)."
    return out


ADU_ORDINANCE = (
    " From the County's ADU ordinance (Ord. 2025-0029, adopted 2025-07-29). In December 2025 the state housing "
    "department (HCD) found parts of it out of line with state ADU law: it leaves out units state law allows, and "
    "its height limits inside Community Standards Districts leave out the 25 ft state law allows for an attached ADU. "
    "The County planned to amend it. "
    "Where state law allows more, state law applies."
)


def county_adu_items(conn, kinds: set[str]) -> list[Item]:
    """The County's own ADU limits, labelled Interpretation: HCD found the ordinance non-compliant in part."""
    ca = R.load("COUNTY_ADU", conn)
    sqft, height, setback = ca.value("max_sqft"), ca.value("height_ft"), ca.value("setback_ft")
    fire = bool({"vhfhsz", "vhfhsz_2025"} & kinds)
    why = None
    if None not in (sqft, height, setback):
        why = (
            f"An ADU of up to {sqft:,.0f} sq ft (22.140.640 G.1.a) and up to {height:g} ft tall, attached or detached "
            f"(G.1.b), at least {setback:g} ft from the rear, interior side and corner side lot lines (G.1.c). On a "
            "single-family lot the County allows one ADU attached to or within the home or an accessory building, one "
            "detached ADU and one JADU (Table 22.140.640-A). A Community Standards District may set a lower height, "
            "but not below 16 ft for a detached ADU."
        )
        why += (
            " This lot is in a Very High Fire Hazard Severity Zone, so parking rules apply (G.1.d.ii)."
            if fire
            else " No parking is required outside a Very High Fire Hazard Severity Zone (G.1.d.i)."
        )
    item = rule_item("county_adu", "adu", "ADU under the County's ordinance", ca, sqft, "sqft", why)
    out = [item]
    if fire:
        fa = R.load("COUNTY_ADU_FIRE", conn)
        out.append(
            Item(
                "flag_county_adu_fire",
                "flag",
                "ADUs in a Very High Fire Hazard Severity Zone",
                True,
                None,
                "interpretive",
                rule_id=fa.rule_id,
                coverage=1.0,
                explanation="On a lot in a Very High Fire Hazard Severity Zone the County prohibits the ADU above "
                "unless the lot has two separate, non-overlapping access roads to a highway, each at least 24 ft wide "
                "and built to Public Works standards, or fronts a highway that cars enter directly (22.140.640 C). "
                "This does not apply to the ADUs state law requires the County to approve (22.140.640 H), such as the "
                "state-law detached ADU above, or to a JADU. The access roads are not checked here.",
                citations=fa.citations(),
            )
        )
    for i in out:
        if i.label == "derived":
            i.label, i.coverage = "interpretive", 1.0
        if i.explanation:
            i.explanation += ADU_ORDINANCE
    return out


def building_types(conn, ctx, lot_area: float | None, kinds: set[str]) -> list[Item]:
    items: list[Item] = []
    st = R.load("ADU_STATE_DETACHED", conn)
    items.append(
        rule_item(
            "adu_state_detached",
            "adu",
            "Detached ADU the County must approve (state law)",
            st,
            st.value("max_sqft"),
            "sqft",
            (
                f"One detached new ADU up to {st.value('max_sqft'):.0f} sq ft, with side and rear setbacks of no more than "
                f"{st.value('setback_ft'):.0f} ft and a height of at least {st.value('height_ft'):.0f} ft allowed, on a lot "
                "with an existing or proposed single-family home. State law requires counties as well as cities to "
                "approve it ministerially (Gov. Code 66323). The County's own ordinance allows more (next item)."
            )
            if None not in (st.value("max_sqft"), st.value("setback_ft"), st.value("height_ft"))
            else None,
        )
    )
    items += county_adu_items(conn, kinds)
    j = R.load("JADU", conn)
    items.append(
        rule_item(
            "jadu",
            "jadu",
            "Junior ADU (inside the home)",
            j,
            j.value("max_sqft"),
            "sqft",
            f"One JADU of up to {j.value('max_sqft'):.0f} sq ft within the single-family home (Gov. Code 66333). A deed "
            "restriction is required, and the owner must live on the lot if the JADU shares a bathroom with the home."
            if j.value("max_sqft")
            else None,
        )
    )
    items.append(
        Item(
            "guest_house",
            "flag",
            "Guest house",
            None,
            None,
            "flag",
            rule_id="FLAG_COUNTY_GUEST_HOUSE",
            explanation="Title 22's use regulations for guest houses (22.18.030, 22.140) are not modeled here.",
        )
    )
    items += sb9_items(conn, ctx, lot_area, kinds, "R1", local="County")
    return items
