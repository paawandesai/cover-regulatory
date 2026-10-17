"""R2 Two-Family (LAMC 12.09) and RE Residential Estate (LAMC 12.07.01) envelopes, for lots off the Hillside Area and
Coastal Zone in Height District 1. Elsewhere the values are withheld: those lots follow LAMC 12.21 C.10 or the
Coastal Zone rules in 12.21.1, which are modeled for R1 only.

Each function returns (items, front, side, rear) like the R1 envelope, so the lot drawing works the same way.
"""

import math

from app.engine import rules as R
from app.engine.geometry import envelope
from app.engine.item import Item, chunk_citation, rule_item

_HD = {"SS": "HD_SS", "VL": "HD_VL", "XL": "HD_XL", "L": "HD_L"}


def _district(conn, hd: str, h: R.RuleInputs, hmax: float | None, why: str | None):
    """Apply a 1L, 1VL, 1XL or 1SS height district on top of the zone's own limit."""
    rule = next((v for k, v in _HD.items() if hd.endswith(k)), None)
    if rule is None or hmax is None:
        return hmax, why
    d = R.load(rule, conn)
    dmax = d.value("max_ft")
    h.found.update({f"district_{k}": v for k, v in d.found.items()})
    if rule == "HD_SS" and dmax is not None:
        return (
            dmax,
            f"Height District {hd} allows one story, with the highest point of the roof at {dmax:g} ft (LAMC 12.21.1 A.1).",
        )
    if dmax is not None and dmax < hmax:
        return dmax, f"Height District {hd} limits buildings to {dmax:g} ft, lower than the zone's {hmax:g} ft."
    return hmax, why


def _withheld(family: str, where: str) -> list[Item]:
    why = f"Not modeled here: this lot is {where}."
    return [
        Item(i, family, t, None, u, "withheld", explanation=why)
        for i, t, u in (
            ("front_yard", "Front yard (minimum)", "ft"),
            ("side_yard", "Side yards (each, minimum)", "ft"),
            ("rear_yard", "Rear yard (minimum)", "ft"),
            ("max_height", "Maximum height", "ft"),
            ("max_rfa", "Maximum floor area", "sqft"),
        )
    ]


def _through(conn, frame, item: Item) -> Item:
    """12.21 C.1(h): a through lot has a front yard at each street end, and no rear yard under 150 ft deep."""
    if frame is not None and frame.through and item.value is not None:
        item.label = "interpretive"
        item.explanation = (
            "This looks like a through lot (streets on opposite sides, detected from the parcel map). A front yard is "
            "then required at each street end, and no rear yard where the lot is under 150 ft deep (LAMC 12.21 "
            "C.1(h)). The drawing uses a front yard at both ends. Confirm the street sides."
        )
        item.citations += chunk_citation(conn, "LAMC 12.21 C.1(h)", "through")
    return item


def _where_unmodeled(kinds: set[str], hd: str) -> str | None:
    if "hillside" in kinds:
        return (
            "in a Hillside Area, where LAMC 12.21 C.10 sets other yards, heights and floor area (modeled for R1 only)"
        )
    if "coastal_zone" in kinds:
        return "in the Coastal Zone, where 12.21.1 sets other heights and floor area (modeled for R1 only)"
    if not hd.startswith("1"):
        return f"in Height District {hd or 'unknown'}; only Height District 1 limits are modeled for this zone"
    return None


def _lot_minimums(fam, zone, lm: R.RuleInputs, lot_area, width) -> Item:
    conforming = None
    if lot_area and width and lm.value("area_sqft") and lm.value("width_ft"):
        conforming = lot_area >= lm.value("area_sqft") and width >= lm.value("width_ft")
    return rule_item(
        "lot_minimums",
        fam,
        f"Lot meets {zone} minimum area and width",
        lm,
        conforming,
        None,
        f"Minimum {lm.value('area_sqft'):,.0f} sq ft and {lm.value('width_ft'):.0f} ft wide. A smaller lot of record may "
        "still be buildable; not evaluated."
        if lm.value("area_sqft") and lm.value("width_ft")
        else None,
    )


def r2_items(conn, ctx, width, depth, lot_area, frame, kinds: set[str]):
    fam, hd = "r2_envelope", (ctx.zone.height_district or "")
    items: list[Item] = []
    use, dens = R.load("R2_USE", conn), R.load("R2_DENSITY", conn)
    per, floor = dens.value("per_unit_sqft"), dens.value("two_family_min_sqft")
    units = None
    if lot_area and per and floor:
        units = min(2, max(1, math.floor(lot_area / per)))
        if lot_area < floor:
            units = 1
    units_item = rule_item(
        "dwelling_units",
        fam,
        "Homes allowed on the lot (R2)",
        R.RuleInputs("R2_DENSITY", {**use.found, **dens.found}),
        units,
        "units",
        f"R2 allows a two-family dwelling or two single-family dwellings (LAMC 12.09 A.2), with at least {per:,.0f} sq "
        f"ft of lot per home and no two-family dwelling on a lot under {floor:,.0f} sq ft (12.09 C.4). This "
        f"{lot_area:,.0f} sq ft lot allows {units:g}. ADUs and a JADU are on top of this (see below). Apartments are "
        "allowed only on lots beside a commercial or industrial zone (12.09 A.3); not evaluated."
        if units is not None
        else "Lot area unknown.",
    )
    items.append(units_item)

    where = _where_unmodeled(kinds, hd)
    lm = R.load("R2_LOT_MINIMUMS", conn)
    if where:
        return [*items, *_withheld(fam, where), _lot_minimums(fam, "R2", lm, lot_area, width)], None, None, None

    # 12.09 C.1-C.3: the R1 yards, cited through both sections.
    yards = R.load("R2_YARDS", conn)
    fy, sy, ry = R.load("R1_FRONT_YARD", conn), R.load("R1_SIDE_YARD", conn), R.load("R1_REAR_YARD", conn)
    for ri, key in ((fy, "front"), (sy, "side"), (ry, "rear")):
        ri.found[f"r2_{key}"] = yards.found[key]
    front = None
    if depth and fy.value("pct") is not None and fy.value("max_ft") is not None:
        front = round(min(depth * fy.value("pct") / 100, fy.value("max_ft")), 1)
    items.append(
        rule_item(
            "front_yard",
            fam,
            "Front yard (minimum)",
            fy,
            front,
            "ft",
            f"Same as R1 (LAMC 12.09 C.1, 12.08 C.1): the lesser of {fy.value('pct'):g}% of lot depth ({depth:.0f} ft) "
            f"and {fy.value('max_ft'):g} ft. A prevailing setback on the block may apply instead; see the estimate below."
            if front is not None
            else "Lot depth unknown.",
        )
    )

    h = R.load("R2_HEIGHT", conn)
    hmax = h.value("max_ft")
    hwhy = f"{hmax:g} ft for R2 off the Hillside Area and Coastal Zone (LAMC 12.21.1)." if hmax else None
    hmax, hwhy = _district(conn, hd, h, hmax, hwhy)

    side = side_base = None
    if width is not None and sy.value("base_ft") is not None:
        if width >= 50 or sy.value("narrow_pct") is None:
            side_base = sy.value("base_ft")
            why = f"Same as R1 (LAMC 12.09 C.2, 12.08 C.2). Lot is {width:.0f} ft wide: {side_base:g} ft up to 18 ft high."
        else:
            side_base = max(round(width * sy.value("narrow_pct") / 100, 1), sy.value("narrow_min_ft") or 0)
            why = (
                f"Same as R1 (LAMC 12.09 C.2, 12.08 C.2). Lot is {width:.0f} ft wide (under 50 ft): "
                f"{sy.value('narrow_pct'):g}% of width, at least {sy.value('narrow_min_ft'):g} ft, up to 18 ft high."
            )
        step = sy.value("per_10ft_over_18_ft")
        side = side_base + (step * math.ceil(max(hmax - 18, 0) / 10) if step and hmax else 0)
        if side != side_base:
            why += (
                f" New construction adds {step:g} ft for each 10 ft (or part) above 18 ft (12.08 C.2(b)), so this "
                f"shows {side:g} ft for a {hmax:g} ft building."
            )
    else:
        why = "Lot width unknown."
    items.append(
        rule_item(
            "side_yard",
            fam,
            f"Side yards (each, minimum, for a {hmax:g} ft building)"
            if side != side_base
            else "Side yards (each, minimum)",
            sy,
            side,
            "ft",
            why,
        )
    )
    items.append(rule_item("max_height", fam, "Maximum height", h, hmax, "ft", hwhy))
    rear = ry.value("min_ft")
    items.append(
        _through(
            conn,
            frame,
            rule_item(
                "rear_yard",
                fam,
                "Rear yard (minimum)",
                ry,
                rear,
                "ft",
                f"Same as R1 (LAMC 12.09 C.3, 12.08 C.3): {rear:g} ft." if rear is not None else None,
            ),
        )
    )

    fa = R.load("R2_FLOOR_AREA", conn)
    x = fa.value("buildable_x")
    side_one = side_base  # 12.03 Buildable Area: yards for a one-story building
    buildable = None
    if frame is not None and x and None not in (front, side_one, rear):
        back = front if frame.through else rear  # a through lot has a front yard at each end
        buildable = envelope(frame, front, side_one, back)["envelope_area_sqft"]
    fa_item = rule_item(
        "max_rfa",
        fam,
        "Maximum floor area (all main buildings)",
        fa,
        round(buildable * x) if buildable else None,
        "sqft",
        f"{x:g} x the buildable area ({buildable:,.0f} sq ft: the lot less a {front:g} ft front, {side_one:g} ft side and "
        f"{back:g} ft {'second front' if frame.through else 'rear'} yard, as for a one-story building), in Height District 1 (LAMC 12.21.1 A.1; Buildable Area "
        "in 12.03). This is Floor Area, not Residential Floor Area: the R1 floor area limit does not apply to R2. "
        "The buildable area comes from the illustrative lot outline; confirm it on a survey."
        if buildable
        else "Buildable area not determined (no lot outline or yards).",
    )
    if fa_item.value is not None:
        fa_item.label, fa_item.coverage = "interpretive", 1.0  # measured on the fitted outline
        fa_item.citations += chunk_citation(conn, "LAMC 12.03(b)", "FLOOR AREA. The area")
    items.append(fa_item)
    items.append(_lot_minimums(fam, "R2", lm, lot_area, width))
    return items, front, side, rear


def re_items(conn, ctx, width, depth, lot_area, frame, kinds: set[str]):
    zone, hd = ctx.zone.base_zone, (ctx.zone.height_district or "")
    fam = "re_envelope"
    needs = R.re_needs(zone)
    lm = R.load(f"{zone}_LOT_MINIMUMS", conn, needs["lot"])
    where = _where_unmodeled(kinds, hd)
    if where:
        return [*_withheld(fam, where), _lot_minimums(fam, zone, lm, lot_area, width)], None, None, None
    items: list[Item] = []

    fy = R.load("RE_FRONT_YARD", conn)
    front = None
    if depth and fy.value("pct") is not None and fy.value("max_ft") is not None:
        front = round(min(depth * fy.value("pct") / 100, fy.value("max_ft")), 1)
    items.append(
        rule_item(
            "front_yard",
            fam,
            "Front yard (minimum)",
            fy,
            front,
            "ft",
            f"The lesser of {fy.value('pct'):g}% of lot depth ({depth:.0f} ft) and {fy.value('max_ft'):g} ft (LAMC "
            "12.07.01 C.1). Where neighbouring lots set a prevailing front yard, that may apply instead; not computed "
            "for RE."
            if front is not None
            else "Lot depth unknown.",
        )
    )

    sy = R.load(f"{zone}_SIDE_YARD", conn, needs["side"])
    side = None
    why = "Lot width unknown."
    if width is not None:
        if zone in ("RE9", "RE11") and sy.value("base_ft") is not None:
            if width >= 70:
                side = sy.value("base_ft")
                why = f"{side:g} ft on a lot {width:.0f} ft wide (70 ft or more) in {zone} (LAMC 12.07.01 C.2(a))."
            else:
                # The 3 ft floor is not a reviewed number, so the narrow-lot value is not computed.
                why = (
                    f"This lot is {width:.0f} ft wide (under 70 ft), so the side yard may be reduced to "
                    f"{sy.value('narrow_pct'):g}% of the width, but not below the floor in LAMC 12.07.01 C.2(a); "
                    "not computed."
                )
        elif zone == "RE15" and sy.value("pct") is not None:
            raw = width * sy.value("pct") / 100
            side = round(min(max(raw, sy.value("min_ft")), sy.value("max_ft")), 1)
            why = (
                f"{sy.value('pct'):g}% of the lot width ({width:.0f} ft), at least {sy.value('min_ft'):g} ft and at most "
                f"{sy.value('max_ft'):g} ft (LAMC 12.07.01 C.2(a))."
            )
        elif sy.value("base_ft") is not None:
            side = sy.value("base_ft")
            why = f"{side:g} ft on each side in {zone} (LAMC 12.07.01 C.2(b))."
        if side is not None:
            why += (
                f" This is for a main building up to two stories and 18 ft. Add {sy.value('per_story_ft'):g} ft for each "
                "story above the second (12.07.01 C.2(c))"
                + (
                    "; for new construction off the Hillside Area and Coastal Zone, 1 ft is added instead for each 10 "
                    "ft (or part) of height above 18 ft"
                    if zone != "RE40"
                    else ""
                )
                + ". The added width is not drawn. A specific plan, HPOZ or subdivision approval may set its own side "
                "yards (12.07.01 C.2(d))."
            )
    side_item = rule_item("side_yard", fam, "Side yards (each, minimum, up to 18 ft high)", sy, side, "ft", why)
    if side is None and width is not None:
        side_item.label = "withheld"  # the rule is cited, but its floor is not a reviewed number
    items.append(side_item)

    h = R.load(f"{zone}_HEIGHT", conn, needs["height"])
    hmax, hlow = h.value("max_ft"), h.value("low_roof_ft")
    hwhy = (
        f"{hmax:g} ft in {zone} off the Hillside Area and Coastal Zone, or {hlow:g} ft where the roof is flat or slopes "
        "less than 25% (LAMC 12.21.1). Where 40% of the homes on the block are taller, their average may apply; not "
        "evaluated."
        if hmax and hlow
        else None
    )
    hmax, hwhy = _district(conn, hd, h, hmax, hwhy)
    items.append(rule_item("max_height", fam, "Maximum height", h, hmax, "ft", hwhy))

    ry = R.load("RE_REAR_YARD", conn)
    rear = None
    if depth and ry.value("pct") is not None and ry.value("max_ft") is not None:
        rear = round(min(depth * ry.value("pct") / 100, ry.value("max_ft")), 1)
    items.append(
        _through(
            conn,
            frame,
            rule_item(
                "rear_yard",
                fam,
                "Rear yard (minimum)",
                ry,
                rear,
                "ft",
                f"The lesser of {ry.value('pct'):g}% of lot depth ({depth:.0f} ft) and {ry.value('max_ft'):g} ft (LAMC "
                "12.07.01 C.3)."
                if rear is not None
                else "Lot depth unknown.",
            ),
        )
    )

    rfa = R.load(f"{zone}_RFA", conn, needs["rfa"])
    pct, val = rfa.value("pct"), None
    if zone in ("RE9", "RE11") and lot_area and lot_area >= 15000:
        # 35% or 6,000 sq ft, whichever is greater: that reading is not reviewed, so no number is shown.
        rfa_why = (
            f"This {zone} lot is 15,000 sq ft or more, where LAMC 12.07.01 C.5 sets 35% of the lot area or 6,000 sq ft, "
            "whichever is greater; that reading is not reviewed yet, so no number is shown."
        )
        rfa_cites = chunk_citation(conn, "LAMC 12.07.01 C.5", "15,000 square feet or greater")
    else:
        val = round(lot_area * pct / 100) if lot_area and pct else None
        rfa_why = (
            f"{pct:g}% of the lot area ({lot_area:,.0f} sq ft), for {zone} off the Hillside Area and Coastal Zone (LAMC "
            "12.07.01 C.5). Another 20% is allowed with an upper-floor step-back or a front-wall step-back (only one "
            "bonus per lot); not included."
            if val
            else "Lot area unknown."
        )
        rfa_cites = []
    rfa_item = rule_item("max_rfa", fam, "Maximum residential floor area", rfa, val, "sqft", rfa_why)
    if rfa_cites:
        rfa_item.label, rfa_item.citations = "withheld", rfa_cites
    items.append(rfa_item)
    items.append(_lot_minimums(fam, zone, lm, lot_area, width))
    return items, front, side, rear
