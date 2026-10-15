"""Buildability assessment for one parcel. Deterministic: no model is called here.

Order: resolve the parcel -> stop early (outside City, Chapter 1A, not R1) -> lot geometry -> rules -> flags.
Every item carries a label (verified / derived / interpretive / uncited) and the citations behind it."""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from app.db.connection import connect
from app.engine import rules as R
from app.engine.geometry import envelope, lot_frame
from app.parcel.provenance import Sourced
from app.parcel.resolve import ParcelContext, resolve

COUNTY_DISCLAIMER = (
    "Parcel boundaries and attributes come from the Los Angeles County Assessor's open parcel data, provided for "
    "informational purposes; it may not be suitable for legal, engineering, or surveying use."
)
TOOL_DISCLAIMER = (
    "Decision support for licensed professionals, not a zoning determination. Confirm every result with LA City "
    "Planning and LADBS before relying on it."
)
AI_DISCLOSURE = (
    "AI was used to read the regulation text into rule candidates. Values labeled 'Interpretation' come from those "
    "readings and have not been reviewed yet; values labeled 'Derived' come from readings a person approved. "
    "No AI model is used to compute this assessment."
)
LABEL_TEXT = {
    "verified": "Verified parcel data",
    "derived": "Derived from rule {rule}",
    "interpretive": "Interpretation, confirm with the jurisdiction",
    "uncited": "No cited source found",
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
        """SELECT id, section_id, source_url, retrieved_at::text AS retrieved_at, left(text, 400) AS excerpt
           FROM reg_chunk WHERE section_id = %s AND (%s::text IS NULL OR text ILIKE '%%' || %s || '%%')
           ORDER BY id LIMIT 1""",
        (section_id, contains, contains),
    ).fetchone()
    if row is None:
        return []
    return [
        {
            "chunk_id": row["id"],
            "section_id": row["section_id"],
            "quote": row["excerpt"],
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
        "derived" if cites else "uncited",
        rule_id=f"FLAG_{fid.upper()}",
        explanation=explanation,
        citations=cites,
    )


def _r1_items(conn, ctx: ParcelContext, width: float | None, depth: float | None, lot_area: float | None):
    items: list[Item] = []
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
            "has a prevailing setback, the average of neighbouring front yards applies instead (up to 40 ft); not "
            "evaluated."
            if depth
            else "Lot depth unknown.",
        )
    )

    sy = R.load("R1_SIDE_YARD", conn)
    side = None
    if width is not None and sy.value("base_ft") is not None:
        if width >= 50 or sy.value("narrow_pct") is None:
            side = sy.value("base_ft")
            why = f"Lot is {width:.0f} ft wide (50 ft or more): {side} ft for a building up to two stories."
        else:
            side = max(round(width * sy.value("narrow_pct") / 100, 1), sy.value("narrow_min_ft") or 0)
            why = (
                f"Lot is {width:.0f} ft wide (under 50 ft): {sy.value('narrow_pct')}% of width, but not less "
                f"than {sy.value('narrow_min_ft')} ft."
            )
        why += (
            " This is for a building up to 18 ft tall. For new construction on flat land, each side yard grows by "
            "1 ft for every 10 ft (or part of 10 ft) of height above 18 ft (LAMC 12.08 C.2(b)), so a 28 ft house "
            "needs 1 ft more and a 33 ft house 2 ft more."
        )
    else:
        why = "Lot width unknown."
    items.append(_rule_item("side_yard", "r1_envelope", "Side yards (each, minimum)", sy, side, "ft", why))

    ry = R.load("R1_REAR_YARD", conn)
    rear = ry.value("min_ft")
    items.append(_rule_item("rear_yard", "r1_envelope", "Rear yard (minimum)", ry, rear, "ft", None))

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
            "Zone. Some floor area (e.g. part of a garage) is exempt, and an encroachment plane starting 20 ft "
            "above the front and side yards shapes the upper floor; neither is evaluated."
            if lot_area
            else None,
        )
    )

    h = R.load("R1_HEIGHT", conn)
    hmax, hlow = h.value("max_ft"), h.value("low_roof_ft")
    hd = (ctx.zone.height_district or "") if ctx.zone else ""
    district = "HD_VL" if hd.endswith("VL") else "HD_XL" if hd.endswith("XL") else None
    why = (
        f"{hmax} ft, or {hlow} ft where the roof is flat or slopes less than 25%. Where 40% of the homes on the block "
        "are taller, their average height may apply instead; not evaluated."
        if hmax and hlow
        else None
    )
    if district:
        d = R.load(district, conn)
        if d.value("max_ft") is not None and hmax is not None and d.value("max_ft") < hmax:
            hmax = d.value("max_ft")
            why = f"Height District {hd} limits buildings to {hmax} ft (lower than the R1 limit)."
            if hlow is not None and hlow < hmax:
                why += f" The R1 limit of {hlow} ft still applies where the roof is flat or slopes less than 25%."
        h.found.update({f"district_{k}": v for k, v in d.found.items()})
    items.append(_rule_item("max_height", "r1_envelope", "Maximum height", h, hmax, "ft", why))

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
            f"{lot_area:,.0f} sq ft. It may not have a kitchen. A guest house with a kitchen is an ADU (see below)."
        )
        if minlot and lot_area
        else None,
    )
    gi.citations += _chunk_citation(conn, "LAMC 12.03", "Accessory Living Quarters")
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
                f"{st.value('setback_ft'):.0f} ft, and a height of at least {st.value('height_ft'):.0f} ft allowed, approved "
                "ministerially on a lot with a single-family home. Taller limits near transit are not evaluated."
            )
            if None not in (st.value("max_sqft"), st.value("setback_ft"), st.value("height_ft"))
            else None,
        )
    )

    lo = R.load("ADU_LOCAL_DETACHED", conn)
    items.append(
        _rule_item(
            "adu_local_detached",
            "adu",
            "Larger detached ADU (City ordinance and state limits)",
            lo,
            lo.value("max_sqft"),
            "sqft",
            (
                f"Up to {lo.value('max_sqft'):.0f} sq ft, {lo.value('setback_ft'):.0f} ft side and rear setbacks. The "
                "City's ordinance was found out of step with state law in 2024; ZA Memo 143 says which parts apply."
            )
            if lo.value("max_sqft") and lo.value("setback_ft")
            else None,
        )
    )

    at = R.load("ADU_ATTACHED", conn)
    existing = (ctx.existing.value or {}).get("sqft_main") if ctx.existing else None
    val = round(existing * at.value("pct_primary") / 100) if existing and at.value("pct_primary") else None
    items.append(
        _rule_item(
            "adu_attached",
            "adu",
            "Attached ADU (maximum floor area)",
            at,
            val,
            "sqft",
            (
                f"{at.value('pct_primary'):.0f}% of the existing home's {existing:,} sq ft (Assessor record). State law "
                "still allows at least 800 sq ft."
            )
            if val
            else "Existing home size unknown.",
        )
    )

    j = R.load("JADU", conn)
    items.append(
        _rule_item(
            "jadu",
            "jadu",
            "Junior ADU (inside the home)",
            j,
            j.value("max_sqft"),
            "sqft",
            f"One JADU of up to {j.value('max_sqft'):.0f} sq ft within the single-family home."
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
                "Rebuild emergency orders apply (EO1 like-for-like; EO8 in the Coastal Zone). Use the "
                "current order instead of the standard rules shown here.",
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
                "verified",
                explanation="Its standards can override the zone's. Not modeled.",
                source={"dataset": "lacity_specific_plans / lacity_hpoz"},
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
                "verified",
                explanation="Q, T or D conditions and supplemental districts are parcel-specific ordinances. "
                "Read them before relying on any value here.",
                source={"dataset": "lacity_zoning"},
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
                "verified",
                explanation="The zone at the parcel's interior point was used.",
                source={"dataset": "lacity_zoning"},
            )
        )
    out.append(
        _flag(
            conn,
            "sb9",
            "SB 9 lot split or two-unit development may be available",
            "State law allows a ministerial two-unit development or lot split on many single-family lots, "
            "with its own eligibility tests. Not evaluated.",
            "Gov. Code 65852.21(a)",
        )
    )
    return out


def assess(query: str) -> dict:
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
        dims = Item(
            "lot_dimensions",
            "parcel",
            "Lot width x depth (from parcel shape)",
            f"{width:.0f} x {depth:.0f}" if width else None,
            "ft",
            "derived" if width else "uncited",
            rule_id="GEOM_ORIENTED_RECTANGLE",
            explanation="Illustrative, not survey-grade: fitted rectangle, front taken as the street-facing "
            "side" + (" (corner lot: shorter street side)." if frame and frame.corner else ".")
            if width
            else "Could not tell which side faces the street.",
        )
        items.append(dims)
        if not ctx.zone.is_plain_r1:
            result["notes"].append(
                f"{ctx.zone.raw} is an R1 variation or carries conditions; the standard R1 values "
                "below are shown for reference and labeled accordingly."
            )
        r1, front, side, rear = _r1_items(conn, ctx, width, depth, lot_area)
        kinds = {o["kind"] for o in ctx.overlays}
        # Flat-land R1 numbers are wrong in the Hillside Area (LAMC 12.21 C.10 replaces them) and the Coastal Zone
        # floor area differs; showing them would mislead, so the values are withheld there.
        withheld = {
            "hillside": {"front_yard", "side_yard", "rear_yard", "max_rfa", "max_height"},
            "coastal_zone": {"max_rfa"},
        }
        for kind, ids in withheld.items():
            if kind in kinds:
                for i in r1:
                    if i.id in ids and i.value is not None:
                        i.value, i.label, i.coverage = None, "uncited", None
                        i.explanation = "Not modeled here: the flat-land rule does not apply in the " + (
                            "Hillside Area." if kind == "hillside" else "Coastal Zone."
                        )
        if "hillside" in kinds:
            front = side = rear = None
        if not ctx.zone.is_plain_r1:
            for i in r1:
                if i.label == "derived":
                    i.label = "interpretive"
                i.explanation = (i.explanation or "") + " Variation or condition not modeled."
        items += r1
        items += _building_types(conn, ctx, lot_area)
        items += _flags(conn, ctx)
    if frame and None not in (front, side, rear):
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
    result["items"] = [asdict(i) | {"label_text": i.label_text} for i in items]
    return result
