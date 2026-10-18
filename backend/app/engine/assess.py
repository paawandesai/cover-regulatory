"""Buildability assessment for one parcel. Deterministic: no model is called here.

Order: resolve the parcel -> stop early (outside City, Chapter 1A, not R1) -> lot geometry -> rules -> flags.
Every item carries a label (verified / derived / interpretive / uncited) and the citations behind it."""

import math
from dataclasses import asdict
from datetime import UTC, datetime

from app.db.connection import connect
from app.engine import county
from app.engine import rules as R
from app.engine.ch1a import ch1a_items
from app.engine.geometry import envelope, lot_frame, rear_neighbour_fronts_side_street
from app.engine.item import Item
from app.engine.item import chunk_citation as _chunk_citation
from app.engine.item import rule_item as _rule_item
from app.engine.orders import rebuild_items, sb9_items
from app.engine.plans import plan_items, unmodeled_plans
from app.engine.prevailing import prevailing
from app.engine.project import ProjectInputs, check_project, summarize
from app.engine.zones import r2_items, re_items
from app.parcel.provenance import Sourced
from app.parcel.resolve import ParcelContext, resolve
from app.parcel.zone import R1_VARIATION, parse_ch1a

COUNTY_DISCLAIMER = (
    "Parcel boundaries and attributes come from the Los Angeles County Assessor's open parcel data, provided for "
    "informational purposes; it may not be suitable for legal, engineering, or surveying use."
)
TOOL_DISCLAIMER = (
    "Decision support for licensed professionals, not a zoning determination. Confirm every result with the "
    "jurisdiction before relying on it: LA City Planning and LADBS in the City, LA County Regional Planning and "
    "Public Works in unincorporated areas."
)
AI_DISCLOSURE = (
    "AI was used to read the regulation text into rule candidates. Values labeled 'Derived' come from readings that "
    "passed review; values labeled 'Interpretation' come from readings not yet reviewed, or depend on a condition the "
    "engine does not model. In this "
    "demo the review was first an AI review applied on the project owner's instruction; the project owner then "
    "approved most of the rules the engine reads, in bulk from a review sheet, and the rest rest on the AI review alone. Each value's source "
    "panel says which. No AI model is used to compute this assessment."
)


def _overlay_source(ctx, kinds: tuple[str, ...]) -> dict:
    rows = [o for o in ctx.overlays if o["kind"] in kinds]
    dates = [o["fetched_at"] for o in rows if o.get("fetched_at")]
    return {
        "dataset": " / ".join(sorted({o["source_id"] for o in rows if o.get("source_id")})) or None,
        "fetched_at": min(dates).isoformat() if dates else None,
    }


def _zone_source(ctx) -> dict:
    z = ctx.zone_strings[0] if ctx.zone_strings else None
    return {
        "dataset": z.source_id if z else None,
        "fetched_at": z.fetched_at.isoformat() if z and z.fetched_at else None,
    }


def _footprints(conn, apn: str) -> tuple[list[dict], Item, float | None]:
    """Existing buildings from the ODbL footprint table: those mostly (over half) inside this parcel."""
    rows = conn.execute(
        """SELECT ST_AsGeoJSON(b.geom)::json AS geom, ST_Area(b.geom::geography) * 10.7639 AS sqft, b.height_m,
                  s.retrieved_at, s.attribution
           FROM parcel p JOIN building_footprint_odbl b ON ST_Intersects(p.geom, b.geom)
           JOIN source s ON s.id = b.source_id
           WHERE p.apn = %s AND ST_Area(ST_Intersection(p.geom, b.geom)) > 0.5 * ST_Area(b.geom)
           ORDER BY sqft DESC""",
        (apn,),
    ).fetchall()
    src = conn.execute(
        "SELECT id, retrieved_at, attribution FROM source WHERE id = 'ms_global_building_footprints'"
    ).fetchone()
    if src is None:
        return (
            [],
            Item(
                "existing_footprint",
                "parcel",
                "Existing buildings (outline)",
                None,
                None,
                "uncited",
                explanation="Building footprints are not loaded.",
            ),
            None,
        )
    total = round(sum(r["sqft"] for r in rows))
    value = f"{len(rows)} building{'s' if len(rows) != 1 else ''}, about {total:,} sq ft" if rows else "None found"
    return (
        [r["geom"] for r in rows],
        Item(
            "existing_footprint",
            "parcel",
            "Existing buildings (outline)",
            value,
            None,
            "approximate",
            explanation="Approximate outlines traced from imagery by machine learning; they can miss, merge or "
            "misplace buildings and may predate recent demolition or construction. Not a survey.",
            source={
                "dataset": src["id"],
                "fetched_at": src["retrieved_at"].isoformat() if src["retrieved_at"] else None,
                "attribution": src["attribution"],
            },
        ),
        (total or None),
    )


def _sourced(item_id: str, title: str, s: Sourced | None, unit: str | None = None) -> Item:
    if s is None or s.value is None:
        return Item(item_id, "parcel", title, None, unit, "uncited", explanation="Not in the loaded data.")
    return Item(
        item_id,
        "parcel",
        title,
        s.value,
        unit,
        "mock" if s.label == "mock" else s.label,
        source={"dataset": s.source_id, "fetched_at": s.fetched_at.isoformat() if s.fetched_at else None},
    )


def _flag(conn, fid, title, explanation, section, contains=None) -> Item:
    cites = _chunk_citation(conn, section, contains)
    return Item(
        fid,
        "flag",
        title,
        True,
        None,
        "flag" if cites else "uncited",
        rule_id=f"FLAG_{fid.upper()}",
        explanation=explanation,
        citations=cites,
    )


def _prevailing_items(conn, ctx: ParcelContext, frame, fy: R.RuleInputs) -> list[Item]:
    """Prevailing front yard and key-lot estimates from neighbouring lots (12.08 C.1). Approximate: they rest on
    parcel and machine-learned building outlines."""
    pv = R.load("R1_PREVAILING_FRONT", conn)
    cap = pv.value("cap_ft")
    if pv.label == "uncited" or cap is None:
        return []
    est = prevailing(conn, ctx.apn, frame, cap) if frame else None
    if est is None:
        item = Item(
            "prevailing_front_yard",
            "r1_envelope",
            "Prevailing front yard on the block (estimate)",
            None,
            "ft",
            "uncited",
            rule_id=pv.rule_id,
            explanation="Could not find the block frontage (fewer than three lots in a row on this street in the "
            "loaded data, or no street side found).",
            citations=pv.citations(),
        )
        return [item]
    counted = est["developed"]
    skipped = "; ".join(f"{e['why']}: {e['apn']}" for e in est["excluded"]) or "none"
    how = (
        f"Block frontage of about {est['frontage_ft']} ft ({est['lots']} lots on this side of the street, found from "
        f"parcel outlines; at most 600 ft each way). {counted} developed lot{'s' if counted != 1 else ''} counted, "
        f"measured to the nearest building outline that is not entirely on the rear half. Not counted: {skipped}."
    )
    if est["combination"]:
        c = est["combination"]
        value = est["value_ft"]
        why = (
            f"{len(c['lots'])} developed lots whose front yards are within 10 ft of each other make up "
            f"{c['share']:.0%} of the frontage, so the minimum front yard is their average, {c['average_ft']:g} ft"
            + (f", capped at {cap:g} ft" if value < c["average_ft"] else "")
            + " (the shallowest such group). If confirmed on a survey this replaces the front yard above. "
        )
    else:
        value = "Not met"
        why = (
            "No group of developed lots with front yards within 10 ft of each other makes up 40% of the frontage, "
            "so the front yard above applies. "
        )
    items = [
        Item(
            "prevailing_front_yard",
            "r1_envelope",
            "Prevailing front yard on the block (estimate)",
            value,
            "ft" if isinstance(value, float) else None,
            "approximate",
            rule_id=pv.rule_id,
            explanation=why + how + " Building outlines are machine-learned and approximate.",
            citations=pv.citations(),
        )
    ]
    key = est.get("key")
    kl = R.load("R1_KEY_LOT", conn)
    sy = R.load("R1_SIDE_YARD", conn)
    if est["key_lot"] and key and kl.value("reach_ft") and key["corner_width_ft"] and sy.value("base_ft") is not None:
        interior = min(key["interior_depth_ft"] * fy.value("pct") / 100, fy.value("max_ft"))
        cw = key["corner_width_ft"]
        corner_side = (
            sy.value("base_ft")
            if cw >= 50 or sy.value("narrow_pct") is None
            else max(round(cw * sy.value("narrow_pct") / 100, 1), sy.value("narrow_min_ft") or 0)
        )
        kv = round((interior + corner_side) / 2, 1)
        k_item = Item(
            "key_lot_front_yard",
            "r1_envelope",
            "Key lot front yard (option, estimate)",
            kv,
            "ft",
            "approximate",
            rule_id=kl.rule_id,
            explanation=(
                f"This looks like a key lot: the lot beside it ({key['corner_apn']}) is a reversed corner lot that "
                "fronts the cross street. The front yard may be the average of the adjoining interior lot's required "
                f"front yard ({interior:g} ft on {key['interior_apn']}) and the corner lot's street-side side yard "
                f"({corner_side:g} ft), so {kv:g} ft, for up to {kl.value('reach_ft'):g} ft from the corner lot's rear "
                "lot line; beyond that the front yard above applies. Where buildings on those lots sit closer, their "
                "yards may be used instead. Lot shapes come from parcel outlines; confirm on a survey."
            ),
            citations=kl.citations() + fy.citations()[:1],
        )
        items.append(k_item)
    return items


def _adu_height(conn, ctx: ParcelContext, st: R.RuleInputs) -> Item:
    """Gov. Code 66321(b)(4): 16 ft for a detached ADU, or 18 ft within half a mile walking distance of a major
    transit stop or high-quality transit corridor. Caltrans' areas are straight-line half-mile buffers; walking
    distance is never shorter, so outside them the 16 ft answer is certain and inside them it is only likely."""
    tr = R.load("ADU_TRANSIT_HEIGHT", conn)
    base, near = st.value("height_ft"), tr.value("height_ft")
    areas = [o for o in ctx.overlays if o["kind"] == "hqta"]
    loaded = conn.execute("SELECT 1 FROM source WHERE id = 'caltrans_hqta'").fetchone() is not None
    title = "Detached ADU height the City must allow"
    if base is None or near is None or not loaded:
        return Item(
            "adu_height", "adu", title, None, "ft", "uncited", explanation="Transit areas or rule text not loaded."
        )
    pitch = _chunk_citation(conn, "Gov. Code 66321(b)", "additional two feet")
    if areas:
        words = {
            "major_stop_rail": "a rail station",
            "major_stop_brt": "a bus rapid transit stop",
            "major_stop_bus": "a stop where frequent bus routes cross",
            "hq_corridor_bus": "a frequent bus corridor",
        }
        kinds = sorted({words.get(o["name"] or "", "a transit area") for o in areas})
        ri = R.RuleInputs("ADU_TRANSIT_HEIGHT", dict(tr.found))
        item = _rule_item(
            "adu_height",
            "adu",
            title,
            ri,
            near,
            "ft",
            f"The lot is within half a mile, in a straight line, of a major transit stop or high-quality transit "
            f"corridor in Caltrans' layer ({', '.join(kinds)}). State law allows {near:g} ft within half a mile "
            f"walking distance, plus 2 ft for a roof pitch that matches the house, so up to {near + 2:g} ft. Walking "
            f"distance can be longer than the straight line; confirm it, or plan for {base:g} ft.",
        )
        item.label = "interpretive"
        item.coverage = 1.0
    else:
        item = _rule_item(
            "adu_height",
            "adu",
            title,
            st,
            base,
            "ft",
            f"{base:g} ft. The {near:g} ft limit near transit does not apply: the lot is more than half a mile, even in "
            "a straight line, from every major transit stop and high-quality transit corridor in Caltrans' layer, "
            "and walking distance is never shorter.",
        )
        item.citations = [c for c in st.citations() if "66321" in (c["section_id"] or "")] + tr.citations()
    if areas:
        item.citations += pitch
    item.source = _overlay_source(ctx, ("hqta",)) if areas else None
    return item


def _hillside_rfa(conn, ctx: ParcelContext, hs: R.RuleInputs, lot_area, zone: str):
    """12.21 C.10(b): the sum over slope bands of band area x ratio, or the guaranteed minimum (25% of the lot or
    800 sq ft) if larger. Band areas are estimated from USGS elevation (app/ingest/slope.py)."""
    bands = [hs.value(f"band_{k}") for k in range(len(R.HILLSIDE_BANDS))]
    ri = R.RuleInputs(hs.rule_id, {k: f for k, f in hs.found.items() if k.startswith("band_") or k == "min_pct"})
    row = conn.execute(
        "SELECT band_sqft, resolution_ft, s.retrieved_at FROM parcel_slope ps JOIN source s ON s.id = ps.source_id "
        "WHERE apn = %s",
        (ctx.apn,),
    ).fetchone()
    floor_cite = _chunk_citation(conn, "LAMC 12.21 C.10(b)", "or 800 square feet, whichever is greater")
    if row is None or None in bands or not lot_area or hs.value("min_pct") is None or not floor_cite:
        return ri, None, "Slope bands for this lot are not computed in the loaded data.", []
    areas = [row["band_sqft"].get(lbl.replace(" ", ""), 0.0) for lbl in R.HILLSIDE_BANDS]
    by_band = sum(a * r for a, r in zip(areas, bands, strict=True))
    minimum = max(lot_area * hs.value("min_pct") / 100, 800)
    value = round(max(by_band, minimum))
    parts = ", ".join(
        f"{lbl}%: {a:,.0f} sq ft x {r:g}" for lbl, a, r in zip(R.HILLSIDE_BANDS, areas, bands, strict=True) if a
    )
    why = (
        f"Sum of each slope band's area times its ratio for {zone} (Tables 12.21 C.10-2a/2b): {parts} = "
        f"{by_band:,.0f} sq ft. The guaranteed minimum is {hs.value('min_pct'):g}% of the lot or 800 sq ft, "
        f"whichever is greater ({minimum:,.0f} sq ft), so the limit is {value:,} sq ft. Slope bands are estimated from "
        f"the USGS 3DEP elevation model on a {row['resolution_ft']:.0f} ft grid; the permit needs a surveyed slope "
        "analysis map, which can differ."
    )
    return ri, value, why, floor_cite


def _r1_items(
    conn,
    ctx: ParcelContext,
    width: float | None,
    depth: float | None,
    lot_area: float | None,
    frame=None,
    design_height: float | None = None,
):
    items: list[Item] = []
    kinds = {o["kind"] for o in ctx.overlays}
    base_zone = (ctx.zone.base_zone or "") if ctx.zone else ""
    hillside = "hillside" in kinds or base_zone.startswith("R1H")
    flat_land = not hillside and "coastal_zone" not in kinds
    fy = R.load("R1_FRONT_YARD", conn)
    front = None
    if depth and fy.value("pct") is not None and fy.value("max_ft") is not None:
        front = round(min(depth * fy.value("pct") / 100, fy.value("max_ft")), 1)
    items.append(
        _rule_item(
            "front_yard",
            "r1_envelope",
            "Front yard (minimum)",
            fy,
            front,
            "ft",
            f"The lesser of {fy.value('pct'):g}% of lot depth ({depth:.0f} ft) and {fy.value('max_ft'):g} ft. Where the block "
            "has a prevailing setback, the average of neighbouring front yards applies instead (up to 40 ft); see the "
            "estimate below."
            if depth
            else "Lot depth unknown.",
        )
    )
    if hillside:
        # Table 12.21 C.10-1 sets the same R1 front, side and rear yards in the Hillside Area.
        items[-1].citations += _chunk_citation(conn, "LAMC 12.21 C.10(a)", "Table 12.21 C.10-1")
    items += _prevailing_items(conn, ctx, frame, fy)

    h = R.load("R1_HEIGHT", conn)
    hmax, hlow = h.value("max_ft"), h.value("low_roof_ft")
    hd = (ctx.zone.height_district or "") if ctx.zone else ""
    district = (
        "HD_SS"
        if hd.endswith("SS")
        else "HD_VL"
        if hd.endswith("VL")
        else "HD_XL"
        if hd.endswith("XL")
        else "HD_L"
        if hd.endswith("L")
        else None
    )
    hwhy = (
        f"{hmax:g} ft off the Hillside Area and Coastal Zone, or {hlow:g} ft where the roof is flat or slopes less than 25%. Where 40% of the homes on the block "
        "are taller, their average height may apply instead; not evaluated."
        if hmax and hlow
        else None
    )
    base = (ctx.zone.base_zone or "") if ctx.zone else ""
    var = None
    h_extra: list[dict] = []
    if R1_VARIATION.match(base) and base[2] in R.VARIATION_TABLE and lot_area:
        # R1V, R1F and R1R have their own height, floor area and lot coverage table (12.08 C.5(b)-(d), 12.21.6).
        var = R.load(f"VARIATION_{base}", conn, R.variation_needs(base, round(lot_area)))
        if base[2] == "V":
            hmax = var.value("height_ft")
            hwhy = (
                f"{base} (Variable-Mass) allows {hmax:g} ft, with the encroachment plane starting {var.value('plane_ft'):g} "
                "ft above the front and side yards and rising at 45 degrees (Table 12.08 C.5.(b)); the plane is not drawn."
                if hmax is not None and var.value("plane_ft") is not None
                else None
            )
        else:
            fh, rh = var.value("front_height_ft"), var.value("rear_height_ft")
            hmax = max(fh, rh) if fh is not None and rh is not None else None
            if hmax is not None:
                if base[2] == "F":
                    hwhy = (
                        f"{base} (Front-Mass, Table 12.08 C.5.(c)): the front mass may reach {fh:g} ft (plane from "
                        f"{var.value('front_plane_ft'):g} ft); the rear mass, at least {var.value('rear_depth_ft'):g} ft deep "
                        f"from the rear yard, is limited to {rh:g} ft (plane from {var.value('rear_plane_ft'):g} ft). "
                        "The planes rise at 45 degrees and are not drawn."
                    )
                elif depth is not None and depth <= 90:
                    hmax = rh
                    hwhy = (
                        f"{base} (Rear-Mass, Table 12.08 C.5.(d)). This lot is {depth:.0f} ft deep (90 ft or less), so "
                        f"the rear mass standard applies to the whole building: {rh:g} ft, plane from "
                        f"{var.value('rear_plane_ft'):g} ft (12.08 C.5(d)(1)(i))."
                    )
                else:
                    hwhy = (
                        f"{base} (Rear-Mass, Table 12.08 C.5.(d)): the front mass, at least {var.value('front_depth_ft'):g} ft "
                        f"deep from the front yard, is limited to {fh:g} ft (plane from {var.value('front_plane_ft'):g} ft); "
                        f"the rear mass may reach {rh:g} ft (plane from {var.value('rear_plane_ft'):g} ft). The planes rise "
                        "at 45 degrees and are not drawn."
                    )
        hlow = None
        h = var
        if base[2] == "R" and depth is not None and depth <= 90:
            h_extra = _chunk_citation(conn, "LAMC 12.08 C.5(d)", "90 feet or less")
    # Coastal Zone, off the Hillside Area, Height District 1: 45 ft (12.21.1) and floor area of three times the
    # buildable area (12.21.1 A.1). Variation zones keep their own table.
    coastal = "coastal_zone" in kinds and "hillside" not in kinds and var is None and hd.startswith("1")
    co = R.load("COASTAL_R1", conn) if coastal else None
    if co is not None and co.value("height_ft") is not None:
        hmax, hlow, h = co.value("height_ft"), None, R.RuleInputs(co.rule_id, {"height_ft": co.found["height_ft"]})
        hwhy = (
            f"{hmax:g} ft for R1 in Height District 1 in the Coastal Zone (LAMC 12.21.1); the 33 ft flat-land limit "
            "does not apply here. A Coastal Development Permit may still limit it."
        )
    hs = None
    hd_row = R.hillside_hd_row(ctx.zone.height_district if ctx.zone else None)
    if hillside:
        district = None  # Table 12.21 C.10-4 already has a row per height district
        hs = R.load(
            "HILLSIDE_R1", conn, R.hillside_needs(base_zone if base_zone.startswith("R1H") else "R1", hd_row or "-")
        )
        h = R.RuleInputs(hs.rule_id, {k: hs.found[k] for k in ("max_ft", "low_roof_ft")})
        hmax, hlow = (hs.value("max_ft"), hs.value("low_roof_ft")) if hd_row else (None, None)
        hwhy = (
            f"Hillside Area, Height District {ctx.zone.height_district}: {hmax:g} ft where the roof slopes 25% or more, "
            f"{hlow:g} ft where it is flatter (Table 12.21 C.10-4). Height is the envelope height above Hillside Area "
            "grade at every point, not above one base point."
            if hmax is not None and hlow is not None
            else "Height district not in Table 12.21 C.10-4."
        )
        if "coastal_zone" in kinds and hmax is not None:
            hwhy += (
                " This lot is also in the Coastal Zone, where 12.21.1 allows 45 ft in Height District 1; 12.21.1 also "
                "sends Hillside lots to this table. Confirm which applies."
            )
    if district:
        d = R.load(district, conn)
        dmax = d.value("max_ft")
        if district == "HD_SS":
            # 1-SS replaces the R1 limit outright: one story and 18 ft to the highest point of the roof.
            hmax = dmax
            hwhy = (
                f"Height District {hd} allows one story, with the highest point of the roof at {dmax:g} ft (LAMC "
                f"12.21.1 A.1). A basement is not a story if the floor above it is no more than "
                f"{d.value('basement_ft'):g} ft above grade."
                if dmax is not None and d.value("basement_ft") is not None
                else f"Height District {hd} limits buildings to one story and 18 ft; the rule text is not reviewed."
            )
        elif dmax is not None and hmax is not None and dmax < hmax:
            hmax = dmax
            hwhy = f"Height District {hd} limits buildings to {hmax:g} ft (lower than the R1 limit)."
            if hlow is not None and hlow < hmax:
                hwhy += f" The R1 limit of {hlow} ft still applies where the roof is flat or slopes less than 25%."
        elif dmax is not None and hwhy:
            hwhy += f" Height District {hd} allows up to {dmax:g} ft, so the R1 limit governs."
        h.found.update({f"district_{k}": v for k, v in d.found.items()})
    sy = R.load("R1_SIDE_YARD", conn)
    side = side_base = None
    hside = hmax
    if width is not None and sy.value("base_ft") is not None:
        if width >= 50 or sy.value("narrow_pct") is None:
            side_base = sy.value("base_ft")
            why = f"Lot is {width:.0f} ft wide (50 ft or more): {side_base:g} ft for a building up to two stories and 18 ft."
        else:
            side_base = max(round(width * sy.value("narrow_pct") / 100, 1), sy.value("narrow_min_ft") or 0)
            why = (
                f"Lot is {width:.0f} ft wide (under 50 ft): {sy.value('narrow_pct'):g}% of width, but not less "
                f"than {sy.value('narrow_min_ft') or 0:g} ft, for a building up to two stories and 18 ft."
            )
        side = side_base
        step = sy.value("per_10ft_over_18_ft")
        hside = min(design_height, hmax) if design_height and hmax else hmax
        if (flat_land or (hillside and "coastal_zone" not in kinds)) and step and hside:
            # 12.08 C.2(b) (and Table 12.21 C.10-1 in the Hillside Area): new construction outside the Coastal Zone
            # adds 1 ft per 10 ft (or part); in the Coastal Zone the per-story rule applies (12.21 C.10(a)(9)(ii)).
            # Shown at the maximum height (or the project's height, when given) so the drawn buildable
            # area is safe for that house.
            extra = step * math.ceil(max(hside - 18, 0) / 10)
            side = side_base + extra
            at = lambda ht: side_base + step * math.ceil(max(ht - 18, 0) / 10)
            why += (
                f" New construction adds {step:.0f} ft for each 10 ft (or part) of height above 18 ft ("
                + ("Table 12.21 C.10-1" if hillside else "LAMC 12.08 C.2(b)")
                + f"), so this shows {side:g} ft for a {hside:g} ft house{' (your project)' if hside != hmax else ' (the maximum)'}. By height: {side_base:g} ft "
                f"up to 18 ft, {at(28):g} ft up to 28 ft, {at(min(hmax, 38)):g} ft up to {min(hmax, 38):g} ft."
            )
        elif not flat_land:
            per = sy.value("per_story_ft")
            why += (
                f" In the Coastal Zone the per-story rule applies instead: add {per:g} ft for each "
                "story above the second ("
                + ("LAMC 12.21 C.10(a)(9)(ii), in lieu of Table 12.21 C.10-1" if hillside else "LAMC 12.08 C.2(a)")
                + ")."
                if per
                else ""
            )
        why += (
            " Walls over 14 ft high and 45 ft long need a 5 ft deep, 10 ft long plane break (enter a wall length "
            "under Your project to check it)."
        )
        if frame is not None and frame.corner:
            why += (
                " Corner lot: LAMC 12.08 C.2 sets no separate street-side yard for R1, so the same side yard applies on "
                "the street side, and a rooftop deck there need not step back the extra 3 ft (12.08 C.2(d))."
            )
    else:
        why = "Lot width unknown."
    items.append(
        _rule_item(
            "side_yard",
            "r1_envelope",
            f"Side yards (each, minimum, for a {hside:g} ft house)"
            if side != side_base
            else "Side yards (each, minimum)",
            sy,
            side,
            "ft",
            why,
        )
    )
    h_item = _rule_item("max_height", "r1_envelope", "Maximum height", h, hmax, "ft", hwhy)
    h_item.citations += h_extra
    if hs is not None and "coastal_zone" in kinds and h_item.value is not None:
        h_item.label, h_item.coverage = "interpretive", 1.0  # two limits may apply; see the explanation
    items.append(h_item)

    ry = R.load("R1_REAR_YARD", conn)
    rear = ry.value("min_ft")
    rear_why = f"{rear:g} ft on every R1 lot, measured from the rear lot line." if rear is not None else None
    ri = _rule_item("rear_yard", "r1_envelope", "Rear yard (minimum)", ry, rear, "ft", rear_why)
    if frame is not None and frame.through and rear is not None:
        # 12.21 C.1(h): a through lot has a front yard at each street end, and no rear yard under 150 ft deep.
        ri.label = "interpretive"
        ri.explanation = (
            "This looks like a through lot (streets on opposite sides, detected from the parcel map). A front yard "
            "is then required at each street end, and no rear yard where the lot is under 150 ft deep (LAMC 12.21 "
            "C.1(h)). The drawing uses a front yard at both ends. Confirm the street sides."
        )
        ri.citations += _chunk_citation(conn, "LAMC 12.21 C.1(h)", "through")
    items.append(ri)

    rfa = var if var is not None else R.load("R1_RFA", conn)
    rfa_val = round(lot_area * rfa.value("ratio")) if lot_area and rfa.value("ratio") is not None else None
    buildable = None
    hs_cites: list[dict] = []
    if hs is not None:
        rfa, rfa_val, rfa_why, hs_cites = _hillside_rfa(conn, ctx, hs, lot_area, base_zone)
    elif co is not None and co.value("buildable_x") is not None:
        rfa = R.RuleInputs(co.rule_id, {"buildable_x": co.found["buildable_x"]})
        rfa.found.update({f"yard_{k}": v for k, v in R.load("R1_FRONT_YARD", conn).found.items()})
        if frame is not None and None not in (front, side_base, rear):
            # 12.03 "Buildable Area": the lot less its required yards, for a one-story building.
            buildable = envelope(frame, front, side_base, front if frame.through else rear)["envelope_area_sqft"]
        rfa_val = round(buildable * co.value("buildable_x")) if buildable else None
        rfa_why = (
            f"{co.value('buildable_x'):g} x the buildable area ({buildable:,.0f} sq ft: the lot less a {front:g} ft front, "
            f"{side_base:g} ft side and {rear:g} ft rear yard, as for a one-story building), for an R1 lot in the "
            "Coastal Zone off the Hillside Area (LAMC 12.21.1 A.1; Buildable Area in 12.03). The buildable area comes "
            "from the illustrative lot outline."
            if buildable
            else "Buildable area not determined (no lot outline or yards)."
        )
    elif var is not None:
        rfa_why = (
            f"{rfa.value('ratio'):g} x lot area ({lot_area:,.0f} sq ft): the {base} ratio for a lot of "
            f"{R.lot_band(round(lot_area)).lower()} sq ft (Table 12.08 C.5.({ {'V': 'b', 'F': 'c', 'R': 'd'}[base[2]] }))."
            if lot_area
            else None
        )
    if co is None and var is None and hs is None:
        rfa_why = (
            f"{rfa.value('ratio')} x lot area ({lot_area:,.0f} sq ft), for a lot outside the Hillside Area and Coastal "
            "Zone. The encroachment plane that starts 20 ft above the front and side yards is not drawn."
            if lot_area
            else None
        )
    rfa_item = _rule_item(
        "max_rfa",
        "r1_envelope",
        "Maximum floor area (Coastal Zone)" if co is not None else "Maximum residential floor area",
        rfa,
        rfa_val,
        "sqft",
        rfa_why,
    )
    if hs is not None and rfa_item.value is not None:
        rfa_item.label, rfa_item.coverage = "interpretive", 1.0  # slope bands are estimated, not surveyed
        rfa_item.citations += hs_cites
    if co is not None and rfa_item.value is not None:
        # The buildable area is measured on the fitted lot outline, which is illustrative.
        rfa_item.label, rfa_item.coverage = "interpretive", 1.0
        rfa_item.explanation += (
            " Here floor area follows the general Floor Area definition (exterior walls, stairways, shafts, equipment "
            "rooms, parking areas and basement storage are not counted), not Residential Floor Area (LAMC 12.03). "
            "Confirm the buildable area on a survey."
        )
        rfa_item.citations += _chunk_citation(conn, "LAMC 12.03(b)", "FLOOR AREA. The area")
    items.append(rfa_item)
    if hs is not None and lot_area and hs.value("coverage_pct") is not None:
        small = bool(width and width < 50 and lot_area < 5000 and hs.value("coverage_small_pct"))
        key = "coverage_small_pct" if small else "coverage_pct"
        pct = hs.value(key)
        items.append(
            _rule_item(
                "max_lot_coverage",
                "r1_envelope",
                "Maximum lot coverage",
                R.RuleInputs(hs.rule_id, {key: hs.found[key]}),
                round(lot_area * pct / 100),
                "sqft",
                f"{pct:g}% of the lot area ({lot_area:,.0f} sq ft) for buildings more than 6 ft above natural ground "
                + ("(substandard lot: under 50 ft wide and under 5,000 sq ft) " if small else "")
                + "(LAMC 12.21 C.10(e)).",
            )
        )
    if var is not None and lot_area and var.value("coverage_pct") is not None:
        cov = R.RuleInputs(var.rule_id, {"coverage_pct": var.found["coverage_pct"]})
        items.append(
            _rule_item(
                "max_lot_coverage",
                "r1_envelope",
                "Maximum lot coverage",
                cov,
                round(lot_area * var.value("coverage_pct") / 100),
                "sqft",
                f"{var.value('coverage_pct'):g}% of the lot area ({lot_area:,.0f} sq ft) may be covered by buildings, "
                f"for a {base} lot of this size.",
            )
        )

    lm = R.load("R1_LOT_MINIMUMS", conn)
    conforming = None
    if lot_area and width and lm.value("area_sqft") and lm.value("width_ft"):
        conforming = lot_area >= lm.value("area_sqft") and width >= lm.value("width_ft")
    items.append(
        _rule_item(
            "lot_minimums",
            "r1_envelope",
            "Lot meets R1 minimum area and width",
            lm,
            conforming,
            None,
            f"Minimum {lm.value('area_sqft'):,.0f} sq ft and {lm.value('width_ft'):.0f} ft wide. A smaller lot of "
            "record may still be buildable; not evaluated."
            if lm.value("area_sqft") and lm.value("width_ft")
            else None,
        )
    )
    return items, front, side, rear


def _building_types(conn, ctx: ParcelContext, lot_area: float | None, family: str = "R1") -> list[Item]:
    items: list[Item] = []
    kinds = {o["kind"] for o in ctx.overlays}
    coastal = "coastal_zone" in kinds
    coastal_note = (
        " In the Coastal Zone a Coastal Development Permit or exemption is still needed: ADU law does not override "
        "the Coastal Act (ZA Memo 143 Rev. 1, Q.23)."
        if coastal
        else ""
    )
    # R2 allows the R1 uses and accessory buildings (12.09 A.1, A.5); RE has its own lot minimum (12.07.01 A.6).
    r2_note = (
        " On an R2 lot with a two-family dwelling, the multifamily ADU rules in Gov. Code 66323(a)(3) and (a)(4) apply "
        "instead; not modeled."
        if family == "R2"
        else ""
    )
    gh = R.load("GUEST_HOUSE_RE" if family == "RE" else "GUEST_HOUSE", conn)
    minlot = gh.value("min_lot_sqft")
    allowed = (lot_area >= minlot) if (lot_area and minlot) else None
    section = {"RE": "LAMC 12.07.01 A.6", "R2": "LAMC 12.09 A.1, 12.08 A.7"}.get(family, "LAMC 12.08 A.7")
    gi = _rule_item(
        "guest_house",
        "guest_house",
        "Guest house (accessory living quarters, no kitchen)",
        gh,
        allowed,
        None,
        (
            f"Allowed as an accessory use only on a lot of at least {minlot:,.0f} sq ft; this lot is "
            f"{lot_area:,.0f} sq ft. Accessory living quarters are for guests only: no kitchen, not rented, at most two "
            f"stories, and they count toward the lot's floor area (LAMC 12.03, {section}). With a kitchen or for rent "
            "it is an ADU instead (see below)."
        )
        if minlot and lot_area
        else None,
    )
    gi.citations += _chunk_citation(conn, "LAMC 12.03", "ACCESSORY LIVING QUARTERS")
    if family == "R2":
        gi.citations += _chunk_citation(conn, "LAMC 12.09 A.1")
    items.append(gi)

    st = R.load("ADU_STATE_DETACHED", conn)
    items.append(
        _rule_item(
            "adu_state_detached",
            "adu",
            "Detached ADU the City must approve (state law)",
            st,
            st.value("max_sqft"),
            "sqft",
            (
                f"One detached new ADU up to {st.value('max_sqft'):.0f} sq ft, with side and rear setbacks of no more than "
                f"{st.value('setback_ft'):.0f} ft, and a height of at least {st.value('height_ft'):.0f} ft allowed, on a lot "
                "with an existing or proposed single-family home. The City must approve it ministerially, including in "
                "a fire hazard or Hillside Area (Gov. Code 66323). See the height the City must allow below."
                + r2_note
                + coastal_note
            )
            if None not in (st.value("max_sqft"), st.value("setback_ft"), st.value("height_ft"))
            else None,
        )
    )

    items.append(_adu_height(conn, ctx, st))

    lo = R.load("ADU_LOCAL_DETACHED", conn)
    lo_item = _rule_item(
        "adu_local_detached",
        "adu",
        "Larger detached ADU (City ordinance and state limits)",
        lo,
        lo.value("max_sqft"),
        "sqft",
        (
            f"Up to {lo.value('max_sqft'):.0f} sq ft, {lo.value('setback_ft'):.0f} ft side and rear setbacks, at most two "
            "stories, not between the house and the street. The lot's floor area limit still applies and may "
            "allow less, but never less than 800 sq ft (LAMC 12.22 A.33(d); ZA Memo 143). The City's ordinance "
            "was found out of step with state law in 2024; ZA Memo 143 says which parts apply." + coastal_note
        )
        if lo.value("max_sqft") and lo.value("setback_ft")
        else None,
    )
    if {"hillside", "vhfhsz"} <= kinds and lo_item.value is not None:
        # Decision path: 12.22 A.33(c)(4) bars Ordinance ADUs on lots in both a VHFHSZ and the Hillside Area (with
        # exceptions), while the state ADU above is exempt. Only the state path is clear here.
        lo_item.label = "interpretive"
        lo_item.explanation = (
            "Two paths on this lot. (1) The state ADU above (800 sq ft) must be approved. (2) This larger City "
            "ordinance ADU is barred on lots in both a Very High Fire Hazard Severity Zone and the Hillside Area "
            "unless the exceptions in LAMC 12.22 A.33(c)(4) are met. If allowed, it may have to provide street "
            "improvements for a 20 ft wide street frontage (ZA Memo 143 Rev. 1, Q.32) and fire sprinklers even where the "
            "house has none (Q.31). Confirm with City Planning before relying on 1,200 sq ft." + coastal_note
        )
        lo_item.citations += _chunk_citation(conn, "LAMC 12.22 A.33(c)", "Hillside Area")
        lo_item.citations += _chunk_citation(conn, "ZA Memo 143 IV", "Q. 42 How")
    items.append(lo_item)

    at = R.load("ADU_ATTACHED", conn)
    existing = (ctx.existing.value or {}).get("sqft_main") if ctx.existing else None
    # 12.22 A.33(e)(3) and Gov. Code 66321(b): an attached ADU of 850 sq ft (1,000 with more than one bedroom) can't
    # be refused, whatever the 50% cap gives.
    floor_cite = _chunk_citation(conn, "LAMC 12.22 A.33(e)", "850 square feet")
    floor = 850 if floor_cite else None
    pct = at.value("pct_primary")
    if existing and pct:
        half = round(existing * pct / 100)
        val = max(half, floor or 0)
        why = (
            f"{pct:.0f}% of the existing home's {existing:,} sq ft (Assessor record) is {half:,} sq ft"
            + (
                f", but an attached ADU of at least {floor:,} sq ft (1,000 sq ft with more than one bedroom) can't be "
                "refused, so {0:,} sq ft applies.".format(val)
                if floor and half < floor
                else "."
            )
            + " The lot's floor area limit still applies above that minimum."
        )
    elif floor and pct:
        val = floor
        why = (
            "No existing home is recorded, so the 50% cap (which applies only to an existing home) doesn't apply. At "
            f"least {floor:,} sq ft (1,000 sq ft with more than one bedroom) can't be refused; a larger attached ADU "
            "is limited by the lot's floor area."
        )
    else:
        val, why = None, "Existing home size unknown."
    at_item = _rule_item(
        "adu_attached", "adu", "Attached ADU (floor area allowed)", at, val, "sqft", why + coastal_note
    )
    at_item.citations += floor_cite
    items.append(at_item)

    j = R.load("JADU", conn)
    items.append(
        _rule_item(
            "jadu",
            "jadu",
            "Junior ADU (inside the home)",
            j,
            j.value("max_sqft"),
            "sqft",
            f"One JADU of up to {j.value('max_sqft'):.0f} sq ft within the single-family home. A deed restriction is "
            "required, and the owner must live on the lot if the JADU shares a bathroom with the home (Gov. Code "
            "66333)."
            if j.value("max_sqft")
            else None,
        )
    )
    return items


# What each zone-change condition can do (LAMC 12.32 G). The conditions themselves are in the zone change ordinance
# for this parcel, found by its case number (City Planning's ZIMAS lists them); those ordinances are not loaded.
_CONDITIONS = {
    "T": (
        "LAMC 12.32 G.1(d)",
        (
            "While in the T (Tentative) classification, the lot may be used only as the earlier zone allowed, until the "
            "map is recorded or the required dedications and improvements are done (12.32 G.1(d))."
        ),
    ),
    "Q": (
        "LAMC 12.32 G.2(a)",
        (
            "A Q (Qualified) condition can bar some of the zone's uses and set its own development standards "
            "(12.32 G.2(a), G.3); on RA, RE, RS and R1 lots it may only mitigate the zone change's environmental effects "
            "(12.32 G.2(j))."
        ),
    ),
    "D": (
        "LAMC 12.32 G.4",
        (
            "A D (Development Limitation) can only lower the height or floor area, or limit lot coverage or setbacks "
            "(12.32 G.4), so any height and floor area shown here are upper limits."
        ),
    ),
}


def _conditions(zone) -> list[str]:
    keys = [k for k in ("T", "Q") if k in zone.prefixes]
    return keys + (["D"] if zone.development_limitation else [])


def _condition_notes(zone) -> str:
    keys = _conditions(zone)
    if not keys:
        return ""
    return (
        " "
        + " ".join(_CONDITIONS[k][1] for k in keys)
        + " The conditions are in the zone change ordinance for this parcel, found by its case number on City "
        "Planning's ZIMAS; that ordinance is not loaded."
    )


def _condition_cites(conn, zone) -> list[dict]:
    out = []
    for k in _conditions(zone):
        out += _chunk_citation(conn, _CONDITIONS[k][0])
    if "Q" in _conditions(zone):
        out += _chunk_citation(conn, "LAMC 12.32 G.2(j)")
    return out


def _flags(conn, ctx: ParcelContext) -> list[Item]:
    kinds = {o["kind"] for o in ctx.overlays}
    out: list[Item] = []
    if "fire_perimeter_2025" in kinds:
        out.append(
            _flag(
                conn,
                "fire_rebuild",
                "Inside a January 2025 fire perimeter",
                "If a building here was damaged or destroyed by the fire, the Mayor's emergency orders offer other "
                "paths than the standard rules: EO 1 (like-for-like rebuild) and, in the Coastal Zone, EO 8 "
                "(zoning-compliant single-family rebuild); see Fire rebuild below. Orders change; check the current "
                "order.",
                "EO 1 B.3",
                "Eligible Projects",
            )
        )
    if "hillside" in kinds:
        out.append(
            _flag(
                conn,
                "hillside",
                "In the Hillside Area",
                "The Hillside Area standards (LAMC 12.21 C.10) are applied above: yards, slope-band floor area, envelope "
                "height and lot coverage. Not evaluated: grading limits (C.10(f)), parking (C.10(g)), fire protection "
                "and street access (C.10(h), (i)), and the sewer connection (C.10(j)).",
                "LAMC 12.21 C.10",
            )
        )
    if "coastal_zone" in kinds:
        out.append(
            _flag(
                conn,
                "coastal",
                "In the Coastal Zone",
                "A Coastal Development Permit may be needed, and Coastal Zone floor area rules differ.",
                "LAMC 12.08 C.5(a)",
            )
        )
    if "vhfhsz" in kinds:
        out.append(
            _flag(
                conn,
                "vhfhsz",
                "Very High Fire Hazard Severity Zone",
                "Additional fire and access rules apply, including for ADUs. Not modeled.",
                "LAMC 12.22 A.33(c)",
                "Very High Fire Hazard",
            )
        )
    if "vhfhsz_2025" in kinds and "vhfhsz" not in kinds:
        # 2025 CAL FIRE map, recommended to the City in March 2025; the City applies it once adopted by ordinance.
        out.append(
            _flag(
                conn,
                "vhfhsz_2025",
                "Very High Fire Hazard Severity Zone on CAL FIRE's 2025 map",
                "The City's current map (the one applied here) does not place this lot in a Very High Fire Hazard "
                "Severity Zone, but CAL FIRE's 2025 recommended map does. Once the City adopts that map, the fire "
                "zone rules apply, including those for ADUs. Check whether it has been adopted.",
                "LAMC 12.22 A.33(c)",
                "Very High Fire Hazard",
            )
        )
    if unmodeled_plans(ctx):
        names = ", ".join(unmodeled_plans(ctx))
        out.append(
            Item(
                "overlay_plan",
                "flag",
                "Specific plan or historic preservation zone",
                names,
                None,
                "flag",
                explanation="Its standards can override the zone's. Not modeled."
                + (
                    " In an HPOZ, exterior work also needs the preservation board's review under the HPOZ rules "
                    "(LAMC 12.20.3, which now points to Chapter 1A Div. 13B.8; not loaded)."
                    if "hpoz" in kinds
                    else ""
                ),
                citations=_chunk_citation(conn, "LAMC 12.20.3") if "hpoz" in kinds else [],
                source=_overlay_source(ctx, ("specific_plan", "hpoz")),
            )
        )
    if ctx.zone and ctx.zone.unmodeled:
        out.append(
            Item(
                "zone_unmodeled",
                "flag",
                "Zone string carries conditions not modeled",
                ", ".join(ctx.zone.unmodeled),
                None,
                "flag",
                explanation="These parts of the zone string change the rules for this parcel (a parcel-specific "
                "ordinance, a height district or a supplemental district). Read them before relying on any value here."
                + _condition_notes(ctx.zone),
                citations=_condition_cites(conn, ctx.zone),
                source=_zone_source(ctx),
            )
        )
    if ctx.split_zoned:
        out.append(
            Item(
                "split_zoned",
                "flag",
                "Parcel is split-zoned",
                True,
                None,
                "flag",
                explanation="Computed: more than 2% of the lot lies in another zone. The zone at the parcel's "
                "interior point was used.",
                source=_zone_source(ctx),
            )
        )
    # SB 9 is evaluated in orders.sb9_items, including Executive Order 9's suspension in the Palisades.

    return out


def _county(ctx: ParcelContext, project, result: dict) -> dict:
    """Unincorporated County land under Title 22. Only Zone R-1 is modeled (app/engine/county.py)."""
    cz = ctx.county_zone
    result["notes"].append(
        "This parcel is in unincorporated Los Angeles County, so the County's zoning code (Title 22) applies, not the "
        "City's. Title 22 was read from a copy whose edition is not stated, so every County value is an Interpretation."
    )
    if not (cz and cz.family):
        result["status"] = "zone_not_modeled"
        result["notes"].append(
            f"County zone {cz.base if cz else 'unknown'} is not modeled. For unincorporated County land this tool models "
            "Zone R-1 only."
        )
        return result
    if not cz.is_modeled:
        result["notes"].append(f"{cz.raw}: " + "; ".join(cz.unmodeled) + ".")
    lot_area = float(ctx.lot_area_sqft.value) if ctx.lot_area_sqft else None
    frame = lot_frame(ctx.apn)
    width = depth = None
    if frame and frame.front_side is not None:
        width, depth = round(frame.width_ft, 1), round(frame.depth_ft, 1)
    kinds = {o["kind"] for o in ctx.overlays}
    with connect() as conn:
        items: list[Item] = [
            Item(
                "lot_dimensions",
                "parcel",
                "Lot width x depth (from parcel shape)",
                f"{width:.0f} x {depth:.0f}" if width else None,
                "ft",
                "approximate" if width else "uncited",
                rule_id="GEOM_ORIENTED_RECTANGLE",
                explanation="Computed from the County parcel outline: a fitted rectangle, with the front taken as the "
                "street-facing side. Illustrative, not survey-grade."
                if width
                else "Could not tell which side faces the street.",
            )
        ]
        buildings, fp_item, _ = _footprints(conn, ctx.apn)
        items.append(fp_item)
        corner = None
        if frame and frame.corner:
            reversed_corner, _ = rear_neighbour_fronts_side_street(frame, ctx.apn)
            corner = "reversed" if reversed_corner else "corner"
        env, front, side, rear = county.envelope_items(conn, ctx, width, depth, lot_area, corner)
        if frame and width and depth and (frame.corner or width > depth):
            # A corner lot's front is its shorter street side; a lot read as wider than deep may be one.
            for i in env:
                if i.id in ("front_yard", "side_yard", "rear_yard"):
                    i.explanation = (i.explanation or "") + (
                        " This lot was read as a corner lot; check which side is the front."
                        if frame.corner
                        else " The front was taken on the lot's long side; if the short side is the front, this "
                        "changes."
                    )
        if not cz.is_modeled:
            for i in env:
                i.explanation = (i.explanation or "") + " Not modeled for this zone: " + "; ".join(cz.unmodeled) + "."
        items += env
        items += county.building_types(conn, ctx, lot_area, kinds)
        items += county.overlay_notes(conn, ctx, env)
    if frame and None not in (front, side, rear):
        result["geometry"] = envelope(frame, front, side, rear) | {
            "yards_ft": {"front": front, "side": side, "rear": rear},
            "buildings": buildings,
        }
    result["items"] = [asdict(i) | {"label_text": i.label_text} for i in items]
    result["summary"] = summarize(items, ctx)
    result["project"] = check_project(items, project, None, False) if project and not project.empty else None
    return result


def assess(query: str, project: "ProjectInputs | None" = None) -> dict:
    ctx = resolve(query)
    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": ctx.status,
        "parcel": {
            "apn": ctx.apn,
            "matched_by": ctx.matched_by,
            "jurisdiction": ctx.jurisdiction_hint,
            "items": [
                asdict(i) | {"label_text": i.label_text}
                for i in [
                    _sourced("lot_area", "Lot area", ctx.lot_area_sqft, "sqft"),
                    _sourced("zone", "Zone", ctx.zone_strings[0] if ctx.zone_strings else None),
                    _sourced("community_plan_area", "Community Plan Area", ctx.community_plan_area),
                    _sourced("code_regime", "Zoning code in effect", ctx.code_regime),
                    _sourced("existing", "Existing building (Assessor)", ctx.existing),
                ]
            ],
        },
        "notes": list(ctx.notes),
        "items": [],
        "geometry": None,
        "disclaimers": [TOOL_DISCLAIMER, COUNTY_DISCLAIMER],
        "ai_disclosure": AI_DISCLOSURE,
    }
    if ctx.status == "outside_city":
        result["notes"] = [
            f"Outside the City of Los Angeles ({ctx.jurisdiction_hint}). This tool models the City and "
            + "unincorporated LA County only."
        ]
        return result
    if ctx.status == "regime_not_modeled":
        z1a = parse_ch1a(ctx.zone_strings[0].value) if ctx.zone_strings else None
        result["notes"].append(
            "This parcel is under the City's new Zoning Code (Chapter 1A). Chapter I rules would be wrong here, so "
            "none are shown."
            + (
                " Only the zone string and the number of homes its Density District allows are modeled."
                if z1a
                else " This tool does not model it."
            )
        )
        if z1a:
            with connect() as conn:
                lot = float(ctx.lot_area_sqft.value) if ctx.lot_area_sqft else None
                items = ch1a_items(conn, z1a, lot, _zone_source(ctx))
            result["items"] = [asdict(i) | {"label_text": i.label_text} for i in items]
        return result
    if ctx.jurisdiction == "lacounty":
        return _county(ctx, project, result)
    if not (ctx.zone and ctx.zone.family):
        result["status"] = "zone_not_modeled"
        result["notes"].append(
            f"Zone {ctx.zone.base_zone if ctx.zone else 'unknown'} is not modeled. This tool models the one-family R1 "
            "zones (with R1V, R1F, R1R and R1H), the R2 two-family zone and the RE9 to RE40 estate zones. "
            "Multiple-dwelling zones such as RD, R3, R4 and R5 have their own density, yard and floor area rules."
        )
        return result
    family = ctx.zone.family

    lot_area = float(ctx.lot_area_sqft.value) if ctx.lot_area_sqft else None
    frame = lot_frame(ctx.apn)
    width = depth = None
    if frame and frame.front_side is not None:
        width, depth = round(frame.width_ft, 1), round(frame.depth_ft, 1)
    with connect() as conn:
        items: list[Item] = []
        long_front = bool(width and depth and width > depth and not frame.corner)
        if not width:
            dims_why = "Could not tell which side faces the street."
        else:
            dims_why = (
                "Computed from the County parcel outline: a fitted rectangle, with the front taken as the "
                "street-facing side"
                + (
                    " (corner lot: the shorter street side)."
                    if frame.corner
                    else " (through lot: streets on opposite sides)."
                    if frame.through
                    else "."
                )
                + " Illustrative, not survey-grade."
            )
            if long_front:
                dims_why += (
                    " Only the long side was read as facing a street. If this is a corner lot, the front is the "
                    "shorter street side and the front yard is larger; confirm on a survey."
                )
        dims = Item(
            "lot_dimensions",
            "parcel",
            "Lot width x depth (from parcel shape)",
            f"{width:.0f} x {depth:.0f}" if width else None,
            "ft",
            "approximate" if width else "uncited",
            rule_id="GEOM_ORIENTED_RECTANGLE",
            explanation=dims_why,
            source={"dataset": "lacounty_parcels", "fetched_at": ctx.lot_area_sqft.fetched_at.isoformat()}
            if width and ctx.lot_area_sqft and ctx.lot_area_sqft.fetched_at
            else None,
        )
        items.append(dims)
        buildings, fp_item, outline_sqft = _footprints(conn, ctx.apn)
        items.append(fp_item)
        if not ctx.zone.is_modeled:
            result["notes"].append(
                f"{ctx.zone.raw}: " + "; ".join(ctx.zone.unmodeled) + ". The values below are shown for reference "
                "and labeled accordingly."
            )
        kinds = {o["kind"] for o in ctx.overlays}
        if family == "R1":
            r1, front, side, rear = _r1_items(
                conn, ctx, width, depth, lot_area, frame, project.height_ft if project else None
            )
        elif family == "R2":
            r1, front, side, rear = r2_items(conn, ctx, width, depth, lot_area, frame, kinds)
            if front is not None:
                # 12.09 C.1 is the R1 front yard, prevailing setback included.
                pv = _prevailing_items(conn, ctx, frame, R.load("R1_FRONT_YARD", conn))
                for it in pv:
                    it.family = "r2_envelope"
                at = next(n for n, i in enumerate(r1) if i.id == "front_yard") + 1
                r1[at:at] = pv
        else:
            r1, front, side, rear = re_items(conn, ctx, width, depth, lot_area, frame, kinds)
        if long_front:
            # The front may really be the short side (an unrecognised corner lot), which swaps width and depth.
            for it in r1:
                if it.id in ("prevailing_front_yard", "key_lot_front_yard"):
                    it.explanation = (it.explanation or "") + (
                        " The front was taken on the lot's long side, so the block used here may be the wrong one."
                    )
                if it.id in ("front_yard", "side_yard") and it.label == "derived":
                    it.label = "interpretive"
                    it.explanation = (it.explanation or "") + (
                        " The front was taken on the lot's long side; if the short side is the front, this changes."
                    )
        # Flat-land R1 numbers are wrong in the Hillside Area (LAMC 12.21 C.10 replaces them) and the Coastal Zone
        # floor area differs; showing them would mislead, so the values are withheld there.
        # The flat-land floor area and 33/28 ft height also exclude the Coastal Zone (12.08 C.5(a), 12.21.1), and the R1
        # variation zones have their own floor area and height tables (12.08 C.5(b), 12.21.6).
        withheld = {
            "coastal_zone_unmodeled": (
                {"max_rfa", "max_height"},
                (
                    "in the Coastal Zone outside Height District 1 (only the Height District 1 coastal limits are "
                    "modeled)."
                ),
            ),
        }
        variation = ctx.zone.base_zone if R1_VARIATION.match(ctx.zone.base_zone or "") else None
        if (
            family == "R1"
            and "coastal_zone" in kinds
            and not variation
            and not (ctx.zone.height_district or "").startswith("1")
        ):
            kinds = kinds | {"coastal_zone_unmodeled"}
        for kind, (ids, where) in withheld.items():
            if kind in kinds:
                for i in r1:
                    if i.id in ids and i.value is not None:
                        i.value, i.label, i.coverage = None, "withheld", None
                        i.explanation = "Not modeled here: the flat-land R1 rule does not apply " + where
        overlay_plan = bool(unmodeled_plans(ctx))  # a plan in app/engine/plans.py is applied, not flagged
        if not ctx.zone.is_modeled or overlay_plan:
            for i in r1:
                if i.label == "derived":
                    i.label = "interpretive"
                i.explanation = (i.explanation or "") + (
                    " Not modeled for this zone string: " + "; ".join(ctx.zone.unmodeled) + "."
                    if not ctx.zone.is_modeled
                    else " A specific plan or HPOZ here can set its own yards and height, which take precedence "
                    f"({'LAMC 12.08 C.2' if family != 'RE' else 'LAMC 12.07.01 C.2(d)'}, 12.21.1); not modeled."
                )
        items += r1
        ex = R.load("RFA_EXEMPTIONS", conn)
        rfa_ex = {k: f.value for k, f in ex.found.items()} if ex.label == "derived" else None
        rfa_item = next((i for i in items if i.id == "max_rfa"), None)
        coastal_floor = "coastal_zone" in kinds and "hillside" not in kinds
        if coastal_floor or family == "R2":
            # R2 is limited by Floor Area (12.21.1 A.1), not Residential Floor Area.
            rfa_ex = None  # 12.03: Residential Floor Area (and its exemptions) does not apply in the Coastal Zone
        if rfa_ex and rfa_item is not None and rfa_item.value is not None:
            rfa_item.explanation = (rfa_item.explanation or "") + (
                f" What counts (LAMC 12.03): area under a ceiling over {rfa_ex['double_ceiling_ft']:g} ft counts twice; "
                f"required covered parking is not counted up to {rfa_ex['parking_max_sqft']:,.0f} sq ft when all of it "
                f"is in the rear half or at least {rfa_ex['parking_front_ft']:g} ft from the front (otherwise "
                f"{rfa_ex['parking_fallback_sqft']:,.0f} sq ft), nor detached accessory buildings of "
                f"{rfa_ex['accessory_each_sqft']:g} sq ft or less, up to {rfa_ex['accessory_total_sqft']:,.0f} sq ft "
                "in all. Lattice-roof porches and qualifying basements are not counted either."
            )
            rfa_item.citations += ex.citations()
        items += _building_types(conn, ctx, lot_area, family)
        items += sb9_items(conn, ctx, lot_area, kinds, family)
        flat = R.load("R1_HEIGHT", conn).value("max_ft") if family == "R1" else None
        items += rebuild_items(conn, ctx, kinds, outline_sqft, flat)
        items += plan_items(conn, ctx)
        items += _flags(conn, ctx)
    if frame and None not in (front, side, rear):
        if frame.through:
            rear = front  # a front yard at each street end (12.21 C.1(h))
        result["geometry"] = envelope(frame, front, side, rear) | {
            "yards_ft": {"front": front, "side": side, "rear": rear}
        }
    elif frame:
        result["geometry"] = envelope(frame, 0, 0, 0) | {
            "envelope": None,
            "envelope_area_sqft": None,
            "yards_ft": None,
            "yards": [],
            "note": "yards not determined; no buildable area drawn",
        }
    if result["geometry"] is not None:
        result["geometry"]["buildings"] = buildings
    result["items"] = [asdict(i) | {"label_text": i.label_text} for i in items]
    result["summary"] = summarize(items, ctx)
    result["project"] = (
        check_project(items, project, rfa_ex, bool(frame and frame.through)) if project and not project.empty else None
    )
    return result
