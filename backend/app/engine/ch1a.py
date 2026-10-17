"""Chapter 1A (the new Zoning Code, in Downtown and Boyle Heights): the zone string and its Density District.

Only Article 1 (the zone string) and Article 6 (density) are loaded. Form, frontage, development standards and use
(Articles 2 to 5) and the CPIO are not, so no envelope is computed and the parcel keeps its "code regime not modeled"
status; the items below are what can be said from the loaded text.
"""

import math

from app.engine import rules as R
from app.engine.item import Item, chunk_citation, rule_item
from app.parcel.zone import Ch1aZone

_LOT_LIMITED = {"1L", "2L", "3L", "4L"}


def ch1a_items(conn, z: Ch1aZone, lot_area: float | None, source: dict | None) -> list[Item]:
    parts = (
        f"Form District {z.form}, Frontage District {z.frontage}, Development Standards District {z.standards}, "
        f"Use District {z.use}, Density District {z.density}"
        + (f"; also {', '.join(z.supplemental)}" if z.supplemental else "")
    )
    items = [
        Item(
            "ch1a_zone",
            "ch1a",
            "Chapter 1A zone string",
            z.raw,
            None,
            "verified",
            explanation=f"{parts}. The first bracket sets the built form, the second the uses and the number of "
            "homes (Ch. 1A Sec. 1.3.1).",
            citations=chunk_citation(conn, "Ch. 1A Sec. 1.3.1", "Zone String Brackets"),
            source=source,
        )
    ]

    d = z.density
    caveats = (
        " Dwellings must also be allowed by the Use District (Article 5, not loaded), and ADUs and JADUs do not count "
        "toward the limit (Sec. 6C.1.1 E, 6C.1.2 E). Affordable housing incentives (Article 9) can allow more."
        + (
            f" This lot also has {', '.join(z.supplemental)}, which is not loaded and may set other limits."
            if z.supplemental
            else ""
        )
    )
    if d in _LOT_LIMITED:
        ri = R.load(f"CH1A_DENSITY_{d}", conn, [R.Need("units", "Ch. 1A Div. 6B.1", "units_per_lot_max", applies=d)])
        units = ri.value("units")
        why = (
            f"Density District {d} allows at most {units:g} dwelling units on a lot, whatever its size (Ch. 1A Div. 6B.1, "
            "Sec. 6C.1.1)." + caveats
            if units is not None
            else None
        )
        item = rule_item("ch1a_density", "ch1a", "Homes allowed by the Density District", ri, units, "units", why)
        item.citations += chunk_citation(conn, "Ch. 1A Sec. 6C.1.1", "regardless of lot area")
    elif d.isdigit():
        ri = R.load(
            f"CH1A_DENSITY_{d}", conn, [R.Need("per_unit", "Ch. 1A Div. 6B.2", "lot_area_per_unit_sqft", applies=d)]
        )
        per = ri.value("per_unit")
        units = math.floor(lot_area / per) if lot_area and per else None
        why = (
            f"Density District {d}: one household dwelling unit per {per:,.0f} sq ft of lot area (Ch. 1A Div. 6B.2). "
            f"This {lot_area:,.0f} sq ft lot allows {units:g}; fractions do not count (Sec. 6C.1.2 D). Half the width of "
            "an adjoining alley may be added to the lot area; not computed. Efficiency units use their own column."
            + caveats
            if units is not None
            else None
        )
        item = rule_item("ch1a_density", "ch1a", "Homes allowed by the Density District", ri, units, "units", why)
        item.citations += chunk_citation(conn, "Ch. 1A Sec. 6C.1.2", "Fractions of units")
    else:
        cites = chunk_citation(conn, "Ch. 1A Sec. 6A.1.3", "FA Density District")
        known = {"FA": "Limited by floor area", "N": "Not permitted"}
        item = Item(
            "ch1a_density",
            "ch1a",
            "Homes allowed by the Density District",
            known.get(d),
            None,
            "interpretive" if d in known and cites else "uncited",
            rule_id="CH1A_DENSITY",
            coverage=1.0 if d in known and cites else None,
            explanation=(
                "Density District FA: no limit on the number of homes beyond what the Form District's floor area "
                "allows (Ch. 1A Sec. 6A.1.3, 6C.1.2 D.4). Form Districts are not loaded, so no number is shown."
                if d == "FA"
                else "Density District N: no household dwelling units are allowed (Sec. 6A.1.3, 6C.1.2 D.5)."
                if d == "N"
                else f"Density District {d} is not in the loaded tables."
            )
            + (caveats if d == "FA" else ""),
            citations=cites,
        )
    if z.supplemental and item.label == "derived":
        item.label, item.coverage = "interpretive", 1.0  # the CPIO (or other district) may change it
    items.append(item)
    items.append(
        Item(
            "ch1a_not_modeled",
            "ch1a",
            "Not modeled: form, frontage, standards and use",
            f"{z.form}, {z.frontage}, {z.standards}, {z.use}",
            None,
            "flag",
            rule_id="FLAG_CH1A",
            explanation="Height, setbacks, floor area, parking and allowed uses come from Chapter 1A Articles 2 to 5, "
            "which are not loaded, so no envelope is shown. Chapter I (R1) rules do not apply here.",
            citations=chunk_citation(conn, "Ch. 1A Sec. 1.3.1", "Article 2. (Form) regulates"),
        )
    )
    return items
