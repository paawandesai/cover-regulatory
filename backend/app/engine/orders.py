"""SB 9 eligibility (Gov. Code 65852.21, 66411.7) and the Mayor's fire rebuild orders (Emergency Executive Orders
1, 8 and 9, January 2025 fires).

Both depend on facts the engine cannot see: who has rented the home, what stood on the lot before the fire, whether
the site is excluded by a statute that is not loaded. So the results say what was checked from the loaded data and
list what must still be confirmed, and stay interpretations unless a test fails outright.
"""

from app.engine import rules as R
from app.engine.item import Item, chunk_citation, rule_item


def _confirm(lines: list[str]) -> str:
    return " Still to confirm: " + "; ".join(lines) + "." if lines else ""


def sb9_items(conn, ctx, lot_area: float | None, kinds: set[str]) -> list[Item]:
    sb = R.load("SB9", conn)
    if sb.label == "uncited":
        return []
    out: list[Item] = []
    if "fire_perimeter_2025" in kinds and "vhfhsz" in kinds:
        eo9 = R.load("EO9_SB9", conn)
        if eo9.label != "uncited":
            why = (
                "Emergency Executive Order 9 (2025-07-30): the City will not accept or process SB 9 applications "
                "(Gov. Code 65852.21 and 66411.7) in the Very High Fire Hazard Severity Zone inside the Palisades "
                "Fire area, and this lot is in both. Applications vested before the Governor's order N-32-25 are "
                "not affected. Check whether the order is still in force."
            )
            for item_id, title in (("sb9_two_unit", "SB 9 two-unit development"), ("sb9_lot_split", "SB 9 lot split")):
                out.append(rule_item(item_id, "sb9", title, eo9, False, None, why))
            return out

    units, protect, setback = sb.value("units"), sb.value("protect_sqft"), sb.value("setback_ft")
    checked = ["the lot is in a single-family zone (R1)"]
    confirm = [
        (
            "no demolition or alteration of rent-restricted or rent-controlled housing, or housing a tenant "
            "occupied in the last 3 years"
        ),
        "no units withdrawn from rent under the Ellis Act in the last 15 years",
        "the site exclusions of Gov. Code 65913.4(a)(6)(B)-(K) as of 2021-09-16 (that section is not loaded)",
    ]
    hazards = [
        name
        for kind, name in (
            ("vhfhsz", "a Very High Fire Hazard Severity Zone"),
            ("fault_zone", "an Alquist-Priolo earthquake fault zone"),
            ("flood_100yr", "a FEMA 100-year flood plain"),
        )
        if kind in kinds
    ]
    site = (
        f" The loaded maps put this lot in {', '.join(hazards)}; 65913.4 excludes some hazard sites unless they meet "
        "its conditions, so check those before relying on this."
        if hazards
        else " The loaded maps show no fire hazard zone, earthquake fault zone or 100-year flood plain here."
    )
    if "hpoz" in kinds:
        confirm.insert(0, "whether the home is a contributing structure in the HPOZ (excluded if it is)")
    else:
        checked.append("no historic preservation overlay (HPOZ) is mapped here")
    two = rule_item(
        "sb9_two_unit",
        "sb9",
        "SB 9 two-unit development",
        R.RuleInputs(sb.rule_id, {k: sb.found[k] for k in ("units", "protect_sqft", "setback_ft")}),
        units,
        "units",
        f"Up to {units:g} homes on the lot, approved ministerially (Gov. Code 65852.21(a)). Local standards may "
        f"not prevent two units of at least {protect:,.0f} sq ft each, and side and rear setbacks may be at most "
        f"{setback:g} ft (none for an existing structure rebuilt in place) (65852.21(b)). Checked: "
        + "; ".join(checked)
        + "."
        + site
        + _confirm(confirm),
    )
    two.label, two.coverage = "interpretive", 1.0  # eligibility rests on facts the loaded data cannot show
    out.append(two)

    pct, min_sqft = sb.value("split_pct"), sb.value("split_sqft")
    split_inputs = R.RuleInputs(sb.rule_id, {k: sb.found[k] for k in ("split_pct", "split_sqft", "split_setback_ft")})
    if lot_area:
        smallest = max(lot_area * pct / 100, min_sqft)
        possible = lot_area >= 2 * min_sqft
        why = (
            f"Two new lots of about equal size, neither under {pct:g}% of the lot ({lot_area * pct / 100:,.0f} sq ft) "
            f"nor under {min_sqft:,.0f} sq ft (Gov. Code 66411.7(a)). "
            + (
                f"This {lot_area:,.0f} sq ft lot can be split into two lots of at least {smallest:,.0f} sq ft "
                "(an equal split gives "
                f"{lot_area / 2:,.0f} sq ft each). Each new lot can then have up to two homes; the City need not "
                "allow more (66411.7(j)). The owner must sign an affidavit to live in one unit for 3 years, and a "
                "lot created by an earlier SB 9 split cannot be split again (66411.7)."
                if possible
                else f"This {lot_area:,.0f} sq ft lot is too small for two lots of {min_sqft:,.0f} sq ft."
            )
            + (" A City ordinance could set a smaller minimum; none is loaded." if not possible else "")
            + (site + _confirm(confirm) if possible else "")
        )
        split = rule_item("sb9_lot_split", "sb9", "SB 9 lot split", split_inputs, possible, None, why)
        split.citations += chunk_citation(conn, "Gov. Code 66411.7(j)", "more than two units")
        if possible:
            split.label, split.coverage = "interpretive", 1.0
        out.append(split)
    return out


def rebuild_items(conn, ctx, kinds: set[str], outline_sqft: float | None, flat_height: float | None) -> list[Item]:
    """Fire rebuild limits for lots inside the January 2025 fire perimeter."""
    if "fire_perimeter_2025" not in kinds:
        return []
    out: list[Item] = []
    eo1 = R.load("EO1_LIKE_FOR_LIKE", conn)
    if eo1.label != "uncited":
        pct = eo1.value("primary_pct")
        assessor = (ctx.existing.value or {}) if ctx.existing else {}
        rec = (
            f" The Assessor records {assessor['sqft_main']:,.0f} sq ft of living area"
            + (f", built {assessor['year_built']}" if assessor.get("year_built") else "")
            + "; that is floor area, not footprint."
            if assessor.get("sqft_main")
            else ""
        )
        why = (
            f'A like-for-like rebuild (EO 1 "Eligible Project") may be up to {pct:g}% of the footprint and of the '
            "height of what stood before the fire, in substantially the same location, for the same use and no "
            "more homes; it then skips discretionary review, nonconforming-use rules and the planning overlays "
            f"(EO 1 B.3). Accessory structures follow the same {eo1.value('accessory_pct'):g}% rule. A new ADU "
            f"qualifies if it is at least {eo1.value('adu_canyon_ft'):g} ft from a canyon bluff or "
            f"{eo1.value('adu_coastal_ft'):g} ft from a coastal bluff (bluffs are not mapped here). Permits are due "
            "within seven years of the order."
        )
        if outline_sqft:
            value = round(outline_sqft * pct / 100)
            why += (
                f" Shown: {pct:g}% of the building outlines on the lot ({outline_sqft:,.0f} sq ft). The outlines are "
                "machine-learned from imagery of unknown date, so they may show the lot before or after the fire; "
                "the City checks the pre-fire footprint against permits, Assessor data and photos (EO 1 B.3)."
            )
        else:
            value = None
            why += (
                " No building outline is loaded for this lot, so the footprint limit is not computed; it is "
                f"{pct:g}% of the pre-fire footprint on record."
            )
        item = rule_item(
            "eo1_footprint", "rebuild", "Like-for-like rebuild footprint (EO 1)", eo1, value, "sqft", why + rec
        )
        if value is not None:
            item.label = "approximate"
        out.append(item)

    eo8 = R.load("EO8_HEIGHT", conn)
    if "coastal_zone" in kinds and "hillside" not in kinds and eo8.label != "uncited" and flat_height:
        out.append(
            rule_item(
                "eo8_height",
                "rebuild",
                "Rebuild height in the Coastal Zone (EO 8)",
                eo8,
                flat_height,
                "ft",
                "A rebuild that is not like-for-like but meets the zoning code can skip the Coastal Development "
                f"Permit under EO 8, if it keeps to {flat_height:g} ft: the flat-land Height District 1 limit, not "
                "the 45 ft Coastal Zone limit (EO 8 A.1). It must replace the same number of homes (plus an ADU), "
                f"stay {eo8.value('canyon_ft'):g} ft from a canyon bluff or {eo8.value('coastal_ft'):g} ft from a "
                "coastal bluff, and involve no lot split or merger. A prevailing front yard that existed before the "
                "fire may be used (EO 8 B.1).",
            )
        )
    return out
