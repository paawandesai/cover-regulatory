"""Buildability assessment for one parcel. Deterministic: no model is called here.

Order: resolve the parcel -> stop early (outside City, Chapter 1A, not R1) -> lot geometry -> rules -> flags.
Every item carries a label (verified / derived / interpretive / uncited) and the citations behind it."""

import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from app.db.connection import connect
from app.engine import rules as R
from app.engine.geometry import envelope, lot_frame
from app.engine.project import ProjectInputs, check_project, summarize
from app.parcel.provenance import Sourced
from app.parcel.resolve import ParcelContext, resolve
from app.parcel.zone import R1_VARIATION

COUNTY_DISCLAIMER = (
    "Parcel boundaries and attributes come from the Los Angeles County Assessor's open parcel data, provided for "
    "informational purposes; it may not be suitable for legal, engineering, or surveying use."
)
TOOL_DISCLAIMER = (
    "Decision support for licensed professionals, not a zoning determination. Confirm every result with LA City "
    "Planning and LADBS before relying on it."
)
AI_DISCLOSURE = (
    "AI was used to read the regulation text into rule candidates. Values labeled 'Derived' come from readings that "
    "passed review; values labeled 'Interpretation' come from readings not yet reviewed, or depend on a condition the "
    "engine does not model. In this "
    "demo that review was an AI review applied on the project owner's instruction, not a person's; each value's "
    "source panel says which. No AI model is used to compute this assessment."
)
LABEL_TEXT = {
    "verified": "Verified parcel data",
    "derived": "Derived from rule {rule}",
    "interpretive": "Interpretation, confirm with the jurisdiction",
    "uncited": "No cited source found",
    "withheld": "Not modeled here",
    "approximate": "Approximate",
    "flag": "Flag, not evaluated",
    "mock": "MOCK data",
}


@dataclass
class Item:
    id: str
    family: str  # parcel | r1_envelope | guest_house | adu | jadu | flag
    title: str
    value: float | str | bool | None
    unit: str | None
    label: str
    rule_id: str | None = None
    coverage: float | None = None
    explanation: str | None = None
    citations: list[dict] = field(default_factory=list)
    source: dict | None = None

    @property
    def label_text(self) -> str:
        return LABEL_TEXT[self.label].format(rule=self.rule_id)


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


def _footprints(conn, apn: str) -> tuple[list[dict], Item]:
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
        return [], Item(
            "existing_footprint",
            "parcel",
            "Existing buildings (outline)",
            None,
            None,
            "uncited",
            explanation="Building footprints are not loaded.",
        )
    total = round(sum(r["sqft"] for r in rows))
    value = f"{len(rows)} building{'s' if len(rows) != 1 else ''}, about {total:,} sq ft" if rows else "None found"
    return [r["geom"] for r in rows], Item(
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


def _rule_item(item_id, family, title, ri: R.RuleInputs, value, unit, explanation) -> Item:
    label = ri.label if value is not None else "uncited"
    return Item(
        item_id,
        family,
        title,
        value,
        unit,
        label,
        rule_id=ri.rule_id,
        coverage=ri.coverage if label == "interpretive" else None,
        explanation=explanation,
        citations=ri.citations(),
    )


def _chunk_citation(conn, section_id: str, contains: str | None = None) -> list[dict]:
    """Cite a chunk by its section id (looked up in code, never emitted by a model)."""
    row = conn.execute(
        """SELECT id, section_id, code_chapter, source_url, retrieved_at::text AS retrieved_at, text
           FROM reg_chunk WHERE section_id = %s AND (%s::text IS NULL OR text ILIKE '%%' || %s || '%%')
           ORDER BY id LIMIT 1""",
        (section_id, contains, contains),
    ).fetchone()
    if row is None:
        return []
    # Quote from the phrase that made this the right chunk (or the start), so the panel highlights it.
    start = max(row["text"].lower().find(contains.lower()), 0) if contains else 0
    end = min(len(row["text"]), start + 400)
    return [
        {
            "chunk_id": row["id"],
            "section_id": row["section_id"],
            "code_chapter": row["code_chapter"],
            "quote": row["text"][start:end],
            "quote_start": start,
            "quote_end": end,
            "source_url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "review_status": "code-cited",
        }
    ]


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
    flat_land = not ({"hillside", "coastal_zone"} & kinds)
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
            f"The lesser of {fy.value('pct')}% of lot depth ({depth:.0f} ft) and {fy.value('max_ft')} ft. Where the block "
            "has a prevailing setback, the average of neighbouring front yards applies instead (up to 40 ft), and a "
            "key lot may average with the neighbouring side yard; neither is evaluated."
            if depth
            else "Lot depth unknown.",
        )
    )

    h = R.load("R1_HEIGHT", conn)
    hmax, hlow = h.value("max_ft"), h.value("low_roof_ft")
    hd = (ctx.zone.height_district or "") if ctx.zone else ""
    district = "HD_VL" if hd.endswith("VL") else "HD_XL" if hd.endswith("XL") else None
    hwhy = (
        f"{hmax} ft off the Hillside Area and Coastal Zone, or {hlow} ft where the roof is flat or slopes less than 25%. Where 40% of the homes on the block "
        "are taller, their average height may apply instead; not evaluated."
        if hmax and hlow
        else None
    )
    if hd.endswith("SS"):
        # 1-SS (one story, 18 ft) is not modeled; showing the R1 33 ft would be wrong.
        hmax = None
        hwhy = "Height District 1-SS limits buildings to one story and 18 ft (LAMC 12.21.1 A.1); not modeled here."
        district = None
    if district:
        d = R.load(district, conn)
        if d.value("max_ft") is not None and hmax is not None and d.value("max_ft") < hmax:
            hmax = d.value("max_ft")
            hwhy = f"Height District {hd} limits buildings to {hmax} ft (lower than the R1 limit)."
            if hlow is not None and hlow < hmax:
                hwhy += f" The R1 limit of {hlow} ft still applies where the roof is flat or slopes less than 25%."
        h.found.update({f"district_{k}": v for k, v in d.found.items()})
    sy = R.load("R1_SIDE_YARD", conn)
    side = side_base = None
    hside = hmax
    if width is not None and sy.value("base_ft") is not None:
        if width >= 50 or sy.value("narrow_pct") is None:
            side_base = sy.value("base_ft")
            why = f"Lot is {width:.0f} ft wide (50 ft or more): {side_base} ft for a building up to two stories and 18 ft."
        else:
            side_base = max(round(width * sy.value("narrow_pct") / 100, 1), sy.value("narrow_min_ft") or 0)
            why = (
                f"Lot is {width:.0f} ft wide (under 50 ft): {sy.value('narrow_pct')}% of width, but not less "
                f"than {sy.value('narrow_min_ft')} ft, for a building up to two stories and 18 ft."
            )
        side = side_base
        step = sy.value("per_10ft_over_18_ft")
        hside = min(design_height, hmax) if design_height and hmax else hmax
        if flat_land and step and hside:
            # 12.08 C.2(b): new construction off the Hillside Area and Coastal Zone adds 1 ft per 10 ft (or part)
            # above 18 ft. Shown at the maximum height (or the project's height, when given) so the drawn buildable
            # area is safe for that house.
            extra = step * math.ceil(max(hside - 18, 0) / 10)
            side = side_base + extra
            at = lambda ht: side_base + step * math.ceil(max(ht - 18, 0) / 10)
            why += (
                f" New construction adds {step:.0f} ft for each 10 ft (or part) of height above 18 ft (LAMC 12.08 "
                f"C.2(b)), so this shows {side:g} ft for a {hside:g} ft house{' (your project)' if hside != hmax else ' (the maximum)'}. By height: {side_base:g} ft "
                f"up to 18 ft, {at(28):g} ft up to 28 ft, {at(min(hmax, 38)):g} ft up to {min(hmax, 38):g} ft."
            )
        elif not flat_land:
            per = sy.value("per_story_ft")
            why += (
                f" In the Coastal Zone or Hillside Area the per-story rule applies instead: add {per:g} ft for each "
                "story above the second (LAMC 12.08 C.2(a))."
                if per
                else ""
            )
        why += " Walls over 14 ft high and 45 ft long need a 5 ft deep, 10 ft long plane break; not evaluated."
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
    items.append(_rule_item("max_height", "r1_envelope", "Maximum height", h, hmax, "ft", hwhy))

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

    rfa = R.load("R1_RFA", conn)
    rfa_val = round(lot_area * rfa.value("ratio")) if lot_area and rfa.value("ratio") is not None else None
    items.append(
        _rule_item(
            "max_rfa",
            "r1_envelope",
            "Maximum residential floor area",
            rfa,
            rfa_val,
            "sqft",
            f"{rfa.value('ratio')} x lot area ({lot_area:,.0f} sq ft), for a lot outside the Hillside Area and Coastal "
            "Zone. Not evaluated: covered parking exemptions (200 sq ft per space, up to 400 sq ft only in the rear half "
            "of the lot), detached accessory buildings up to 200 sq ft, open lattice-roof porches, double counting of "
            "ceilings over 14 ft, and the encroachment plane that starts 20 ft above the front and side yards."
            if lot_area
            else None,
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


def _building_types(conn, ctx: ParcelContext, lot_area: float | None) -> list[Item]:
    items: list[Item] = []
    kinds = {o["kind"] for o in ctx.overlays}
    coastal = "coastal_zone" in kinds
    coastal_note = (
        " In the Coastal Zone a Coastal Development Permit or exemption is still needed: ADU law does not override "
        "the Coastal Act (ZA Memo 143, Q.23)."
        if coastal
        else ""
    )
    gh = R.load("GUEST_HOUSE", conn)
    minlot = gh.value("min_lot_sqft")
    allowed = (lot_area >= minlot) if (lot_area and minlot) else None
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
            "stories, and they count toward the lot's residential floor area (LAMC 12.03, 12.08 A.7). With a kitchen "
            "or for rent it is an ADU instead (see below)."
        )
        if minlot and lot_area
        else None,
    )
    gi.citations += _chunk_citation(conn, "LAMC 12.03", "ACCESSORY LIVING QUARTERS")
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
                "a fire hazard or Hillside Area (Gov. Code 66323). Taller limits (18 ft near transit or with a matching "
                "roof pitch) are not evaluated." + coastal_note
            )
            if None not in (st.value("max_sqft"), st.value("setback_ft"), st.value("height_ft"))
            else None,
        )
    )

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
            "unless the exceptions in LAMC 12.22 A.33(c)(4) are met, and street dedications may still be required "
            "(ZA Memo 143, Q.42). Confirm with City Planning before relying on 1,200 sq ft." + coastal_note
        )
        lo_item.citations += _chunk_citation(conn, "LAMC 12.22 A.33(c)", "Hillside Area")
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


def _flags(conn, ctx: ParcelContext) -> list[Item]:
    kinds = {o["kind"] for o in ctx.overlays}
    out: list[Item] = []
    if "fire_perimeter_2025" in kinds:
        out.append(
            _flag(
                conn,
                "fire_rebuild",
                "Inside a January 2025 fire perimeter",
                "If a building here was damaged or destroyed by the fire, the Mayor's emergency orders may apply "
                "instead of the standard rules: EO 1 (like-for-like rebuild), EO 8 (single-family homes in the Coastal "
                "Zone), and EO 9 (no SB 9 projects in the burn area's fire hazard zone). Cited from City Planning's "
                "rebuild FAQ, not the orders themselves; check the current order.",
                "Palisades Rebuild FAQ Q1",
            )
        )
    if "hillside" in kinds:
        out.append(
            _flag(
                conn,
                "hillside",
                "In the Hillside Area",
                "Hillside rules replace the flat-land R1 envelope (setbacks, floor area, height, grading). "
                "Not modeled; the flat-land values above do not apply.",
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
    if "specific_plan" in kinds or "hpoz" in kinds:
        names = ", ".join(sorted({o["name"] for o in ctx.overlays if o["kind"] in ("specific_plan", "hpoz")}))
        out.append(
            Item(
                "overlay_plan",
                "flag",
                "Specific plan or historic preservation zone",
                names,
                None,
                "flag",
                explanation="Its standards can override the zone's. Not modeled.",
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
                "ordinance, an R1 variation table, a height district or a supplemental district). Read them before "
                "relying on any value here.",
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
    if "fire_perimeter_2025" in kinds and "vhfhsz" in kinds:
        out.append(
            _flag(
                conn,
                "sb9_suspended",
                "SB 9 is suspended here",
                "Mayor's Executive Order 9 suspends SB 9 lot splits and two-unit projects in the Very High Fire Hazard "
                "Severity Zone inside the Palisades burn area. Check whether the order is still in force.",
                "Palisades Rebuild FAQ Q13",
                "Senate Bill 9",
            )
        )
    else:
        out.append(
            _flag(
                conn,
                "sb9",
                "SB 9 lot split or two-unit development may be available",
                "State law allows a ministerial two-unit development or lot split on many single-family lots. It "
                "excludes, among others, Very High Fire Hazard Severity Zones (unless fire standards are met), "
                "historic districts and landmarks, flood zones, and homes rented in the last 3 years for a lot "
                "split. "
                + ("This lot is in a Very High Fire Hazard Severity Zone. " if "vhfhsz" in kinds else "")
                + "Not evaluated.",
                "Gov. Code 65852.21(a)",
            )
        )
    return out


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
            f"Outside the City of Los Angeles ({ctx.jurisdiction_hint}). This tool models City zoning only."
        ]
        return result
    if ctx.status == "regime_not_modeled":
        result["notes"].append(
            "This parcel is under the City's new Zoning Code (Chapter 1A), which this tool does "
            "not model. Chapter I rules would be wrong here, so none are shown."
        )
        return result
    if not (ctx.zone and ctx.zone.is_r1_family):
        result["status"] = "zone_not_modeled"
        result["notes"].append("Only the R1 one-family zone family is modeled.")
        return result

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
        buildings, fp_item = _footprints(conn, ctx.apn)
        items.append(fp_item)
        if not ctx.zone.is_plain_r1:
            result["notes"].append(
                f"{ctx.zone.raw} is an R1 variation or carries conditions; the standard R1 values "
                "below are shown for reference and labeled accordingly."
            )
        r1, front, side, rear = _r1_items(
            conn, ctx, width, depth, lot_area, frame, project.height_ft if project else None
        )
        if long_front:
            # The front may really be the short side (an unrecognised corner lot), which swaps width and depth.
            for it in r1:
                if it.id in ("front_yard", "side_yard") and it.label == "derived":
                    it.label = "interpretive"
                    it.explanation = (it.explanation or "") + (
                        " The front was taken on the lot's long side; if the short side is the front, this changes."
                    )
        kinds = {o["kind"] for o in ctx.overlays}
        # Flat-land R1 numbers are wrong in the Hillside Area (LAMC 12.21 C.10 replaces them) and the Coastal Zone
        # floor area differs; showing them would mislead, so the values are withheld there.
        # The flat-land floor area and 33/28 ft height also exclude the Coastal Zone (12.08 C.5(a), 12.21.1), and the R1
        # variation zones have their own floor area and height tables (12.08 C.5(b), 12.21.6).
        withheld = {
            "hillside": ({"front_yard", "side_yard", "rear_yard", "max_rfa", "max_height"}, "in the Hillside Area."),
            "coastal_zone": (
                {"max_rfa", "max_height"},
                (
                    "in the Coastal Zone (Height District 1 allows up to 45 ft there, subject to a Coastal Development "
                    "Permit; Coastal Zone floor area rules differ)."
                ),
            ),
        }
        variation = ctx.zone.base_zone if R1_VARIATION.match(ctx.zone.base_zone or "") else None
        if variation:
            withheld["variation"] = (
                {"max_rfa", "max_height"},
                (
                    f"in the {variation} One-Family Zone Variation, which has its own floor area and height table "
                    "(LAMC 12.08 C.5(b), 12.21.6)."
                ),
            )
            kinds = kinds | {"variation"}
        for kind, (ids, where) in withheld.items():
            if kind in kinds:
                for i in r1:
                    if i.id in ids and i.value is not None:
                        i.value, i.label, i.coverage = None, "withheld", None
                        i.explanation = "Not modeled here: the flat-land R1 rule does not apply " + where
        if "hillside" in kinds:
            front = side = rear = None
        overlay_plan = bool({"specific_plan", "hpoz"} & kinds)
        if not ctx.zone.is_plain_r1 or overlay_plan:
            for i in r1:
                if i.label == "derived":
                    i.label = "interpretive"
                i.explanation = (i.explanation or "") + (
                    " Variation or condition not modeled."
                    if not ctx.zone.is_plain_r1
                    else " A specific plan or HPOZ here can set its own yards and height, which take precedence "
                    "(LAMC 12.08 C.2, 12.21.1); not modeled."
                )
        items += r1
        items += _building_types(conn, ctx, lot_area)
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
            "note": "yards not determined; no buildable area drawn",
        }
    if result["geometry"] is not None:
        result["geometry"]["buildings"] = buildings
    result["items"] = [asdict(i) | {"label_text": i.label_text} for i in items]
    result["summary"] = summarize(items, ctx)
    result["project"] = check_project(items, project) if project and not project.empty else None
    return result
