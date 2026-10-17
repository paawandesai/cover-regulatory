"""Rule catalogue: which reviewed fragments each deterministic rule reads.

A rule's logic (a formula) is written here in code. Its numbers come from rule fragments, found by section,
parameter and a phrase their quote must contain. The label follows the fragment's review state:
  approved fragment          -> "derived"      ("Derived from rule <id>")
  pending, passed checks     -> "interpretive" (a model reading nobody has reviewed yet)
  missing / invalid / stale  -> the input is unknown, and the rule says so
"""

from dataclasses import dataclass, field

from app.db.connection import connect
from app.engine.links import deep_link


@dataclass(frozen=True)
class Need:
    key: str
    section: str  # exact section id or prefix ending in "*"
    parameter: str
    quote_has: str | None = None
    pick: str = "one"  # "one" | "max" | "min"
    numeric: bool = True  # False: a rule stated in words (its logic is in code); found when cited text exists
    applies: str | None = None  # the fragment's applies_to must include this (a table column, e.g. "R1V2")
    condition_has: str | None = None  # the fragment's conditions must contain this (a table row)


@dataclass
class Found:
    value: float | None
    fragment_ids: list[int]
    citations: list[dict]
    status: str  # approved | pending | missing | ambiguous


@dataclass
class RuleInputs:
    rule_id: str
    found: dict[str, Found] = field(default_factory=dict)

    @property
    def label(self) -> str:
        states = {f.status for f in self.found.values()}
        if not states or states & {"missing", "ambiguous"}:
            return "uncited"
        return "derived" if states == {"approved"} else "interpretive"

    @property
    def coverage(self) -> float:
        """Share of this rule's inputs found in cited, check-passing text. Shown for interpretive results."""
        if not self.found:
            return 0.0
        return round(sum(f.status in ("approved", "pending") for f in self.found.values()) / len(self.found), 2)

    def value(self, key: str) -> float | None:
        return self.found[key].value if key in self.found else None

    def citations(self) -> list[dict]:
        seen, out = set(), []
        for f in self.found.values():
            for c in f.citations:
                if c["fragment_id"] not in seen:
                    seen.add(c["fragment_id"])
                    out.append(c)
        return out


RULES: dict[str, list[Need]] = {
    "R1_FRONT_YARD": [
        Need("pct", "LAMC 12.08 C.1", "front_yard_pct_lot_depth", "front yard of not less than"),
        Need("max_ft", "LAMC 12.08 C.1", "front_yard_max_ft", "front yard of not less than"),
    ],
    "R1_SIDE_YARD": [
        Need("base_ft", "LAMC 12.08 C.2", "side_yard_min_ft", "not more than two stories"),
        Need("narrow_pct", "LAMC 12.08 C.2", "side_yard_pct_lot_width", "less than 50 feet"),
        Need("narrow_min_ft", "LAMC 12.08 C.2", "side_yard_min_ft", "less than 50 feet"),
        Need("per_story_ft", "LAMC 12.08 C.2", "side_yard_extra_per_story_ft", "more than two stories"),
        Need("per_10ft_over_18_ft", "LAMC 12.08 C.2", "other", "above the first 18 feet"),
    ],
    "R1_REAR_YARD": [Need("min_ft", "LAMC 12.08 C.3", "rear_yard_min_ft")],
    "R1_LOT_MINIMUMS": [
        Need("area_sqft", "LAMC 12.08 C.4", "lot_area_min_sqft"),
        Need("width_ft", "LAMC 12.08 C.4", "lot_width_min_ft"),
    ],
    "R1_RFA": [Need("ratio", "LAMC 12.08 C.5(a)", "rfa_ratio", "outside of a Hillside Area")],
    "R1_HEIGHT": [
        Need("max_ft", "LAMC 12.21.1", "height_max_ft", "R1, RS, or RE9", pick="max"),
        Need("low_roof_ft", "LAMC 12.21.1", "height_max_ft", "R1, RS, or RE9", pick="min"),
    ],
    "HD_VL": [Need("max_ft", "LAMC 12.21.1 A.1", "height_max_ft", "“VL”")],
    "HD_XL": [Need("max_ft", "LAMC 12.21.1 A.1", "height_max_ft", "“XL”")],
    "HD_L": [Need("max_ft", "LAMC 12.21.1 A.1", "height_max_ft", "“L”")],
    "HD_SS": [
        Need("max_ft", "LAMC 12.21.1 A.1", "height_max_ft", "“SS”"),
        Need("stories", "LAMC 12.21.1 A.1", "stories_max", "“SS”"),
        Need("basement_ft", "LAMC 12.21.1 A.1", "other", "Basement does not count"),
    ],
    # Prevailing front yard (12.08 C.1). The 10 ft spread, 40% of frontage and shallowest-average logic is coded in
    # app/engine/prevailing.py; each phrase below must be in the reviewed quote for the rule to run.
    "R1_PREVAILING_FRONT": [
        Need(
            "rule",
            "LAMC 12.08 C.1",
            "front_yard_min_ft",
            "vary in depth by not more than ten feet comprise 40%",
            numeric=False,
        ),
        Need("shallowest", "LAMC 12.08 C.1", "front_yard_min_ft", "shallowest average depth", numeric=False),
        Need("cap_ft", "LAMC 12.08 C.1", "other", "exceed 40 feet in depth"),
    ],
    "R1_KEY_LOT": [
        Need("reach_ft", "LAMC 12.08 C.1", "other", "On key lots the minimum front yard may be the average")
    ],
    "R1_PLANE_BREAK": [
        Need(
            "rule",
            "LAMC 12.08 C.2",
            "other",
            "exceeding 14 feet in height and a continuous length greater than 45 feet",
            numeric=False,
        )
    ],
    # SB 9: two-unit development (Gov. Code 65852.21) and urban lot split (66411.7).
    "SB9": [
        Need("units", "Gov. Code 65852.21(a)", "sb9_units_per_lot_max", "no more than two residential units"),
        Need("protect_sqft", "Gov. Code 65852.21(b)", "sb9_unit_min_floor_area_sqft", "800 square feet"),
        Need("setback_ft", "Gov. Code 65852.21(b)", "sb9_side_rear_setback_ft", "four feet"),
        Need("split_pct", "Gov. Code 66411.7(a)", "sb9_lot_split_min_pct", "40 percent"),
        Need("split_sqft", "Gov. Code 66411.7(a)", "sb9_lot_split_min_sqft", "1,200 square feet"),
        Need("split_setback_ft", "Gov. Code 66411.7(c)", "sb9_side_rear_setback_ft", "four feet"),
    ],
    "EO9_SB9": [Need("suspended", "EO 9 1", "sb9_suspended", "will not accept or process", numeric=False)],
    # Mayor's Emergency Executive Orders 1 (revised) and 8 after the January 2025 fires.
    "EO1_LIKE_FOR_LIKE": [
        Need("primary_pct", "EO 1 B.3", "rebuild_max_pct_prior", "Primary structures"),
        Need("accessory_pct", "EO 1 B.3", "rebuild_max_pct_prior", "Accessory structures"),
        Need("adu_canyon_ft", "EO 1 B.3", "rebuild_bluff_setback_ft", condition_has="Canyon"),
        Need("adu_coastal_ft", "EO 1 B.3", "rebuild_bluff_setback_ft", condition_has="Coastal"),
    ],
    "EO8_HEIGHT": [
        Need("height", "EO 8 A", "height_max_ft", "Non-hillside R1 properties", numeric=False),
        Need("canyon_ft", "EO 8 A", "rebuild_bluff_setback_ft", condition_has="Canyon"),
        Need("coastal_ft", "EO 8 A", "rebuild_bluff_setback_ft", condition_has="Coastal"),
    ],
    "RFA_EXEMPTIONS": [
        Need("double_ceiling_ft", "LAMC 12.03(b)", "rfa_double_count_ceiling_ft", "greater than 14 feet"),
        Need("parking_max_sqft", "LAMC 12.03(b)", "rfa_parking_exempt_sqft", "200 square feet per parking space"),
        Need("parking_fallback_sqft", "LAMC 12.03(b)", "rfa_parking_exempt_sqft", "only 200 square feet"),
        Need("parking_front_ft", "LAMC 12.03(b)", "rfa_parking_front_setback_ft", "rear half of the Lot"),
        Need("parking_through_ft", "LAMC 12.03(b)", "rfa_parking_front_setback_ft", "Through Lot"),
        Need("accessory_each_sqft", "LAMC 12.03(c)", "rfa_accessory_exempt_sqft", "Detached Accessory", pick="min"),
        Need("accessory_total_sqft", "LAMC 12.03(c)", "rfa_accessory_exempt_sqft", "Detached Accessory", pick="max"),
    ],
    "COASTAL_R1": [
        Need("height_ft", "LAMC 12.21.1", "height_max_ft", "located in a Coastal Zone"),
        Need("buildable_x", "LAMC 12.21.1 A.1", "rfa_ratio", "Coastal Zone not located in a Hillside Area"),
    ],
    "ADU_TRANSIT_HEIGHT": [Need("height_ft", "Gov. Code 66321(b)", "adu_height_max_ft", "major transit stop")],
    "GUEST_HOUSE": [Need("min_lot_sqft", "LAMC 12.08 A.7", "alq_min_lot_area_sqft")],
    "ADU_STATE_DETACHED": [
        Need("max_sqft", "Gov. Code 66323(a)", "adu_max_floor_area_sqft", "800 square feet"),
        Need("setback_ft", "Gov. Code 66323(a)", "adu_side_rear_setback_ft", "One detached, new construction"),
        Need("height_ft", "Gov. Code 66321(b)", "adu_height_max_ft", "16 feet"),
    ],
    "ADU_LOCAL_DETACHED": [
        Need("max_sqft", "LAMC 12.22 A.33(d)", "adu_max_floor_area_sqft", "detached ADU"),
        Need("state_max_sqft", "Gov. Code 66314(d)", "adu_max_floor_area_sqft", "detached"),
        Need("setback_ft", "Gov. Code 66314(d)", "adu_side_rear_setback_ft"),
        Need("height_ft", "Gov. Code 66321(b)", "adu_height_max_ft", "16 feet"),
    ],
    "ADU_ATTACHED": [Need("pct_primary", "Gov. Code 66314(d)", "adu_max_floor_area_pct_primary")],
    "JADU": [
        Need("max_sqft", "Gov. Code 66313(d)", "jadu_max_floor_area_sqft"),
        Need("count", "Gov. Code 66333(a)", "jadu_count_max"),
    ],
}


def _section_clause(section: str) -> tuple[str, str]:
    if section.endswith("*"):
        return "c.section_id LIKE %s", section[:-1] + "%"
    return "c.section_id = %s", section


def _citation(r) -> dict:
    return {
        "fragment_id": r["id"],
        "chunk_id": r["chunk_id"],
        "section_id": r["section_id"],
        "code_chapter": r["code_chapter"],
        "quote": r["source_quote"],
        "quote_start": r["quote_start"],
        "quote_end": r["quote_end"],
        "review_status": r["status"],
        "reviewed_by": r["reviewed_by"],
        "source_url": deep_link(r["source_url"], r["section_id"], r["page_start"]),
        "retrieved_at": r["retrieved_at"],
    }


def load(rule_id: str, conn=None, needs: list[Need] | None = None) -> RuleInputs:
    if conn is None:
        with connect() as c:
            return load(rule_id, c, needs)
    out = RuleInputs(rule_id)
    for need in needs if needs is not None else RULES[rule_id]:
        clause, arg = _section_clause(need.section)
        rows = conn.execute(
            f"""SELECT f.id, f.status, f.reviewed_by, f.value_numeric, f.source_quote, f.quote_start, f.quote_end, f.chunk_id,
                       c.section_id, c.code_chapter, c.source_url, c.page_start, c.retrieved_at::text AS retrieved_at
                FROM rule_fragment f JOIN reg_chunk c ON c.id = f.chunk_id
                WHERE {clause} AND f.parameter = %s AND f.status IN ('approved', 'pending')
                  AND f.validation = 'ok' AND f.chunk_hash = c.content_hash AND NOT c.mock
                  AND (%s::text IS NULL OR f.source_quote ILIKE '%%' || %s || '%%')
                  AND (%s::text IS NULL OR %s = ANY(f.applies_to))
                  AND (%s::text IS NULL OR f.conditions ILIKE '%%' || %s || '%%')
                ORDER BY (f.status = 'approved') DESC, f.id""",
            (
                arg,
                need.parameter,
                need.quote_has,
                need.quote_has,
                need.applies,
                need.applies,
                need.condition_has,
                need.condition_has,
            ),
        ).fetchall()
        # An approved reading outranks unreviewed ones for the same input.
        if any(r["status"] == "approved" for r in rows):
            rows = [r for r in rows if r["status"] == "approved"]
        values = sorted({float(r["value_numeric"]) for r in rows if r["value_numeric"] is not None})
        if not need.numeric:
            rows = rows[:1]
            values = []
            if not rows:
                out.found[need.key] = Found(None, [], [], "missing")
                continue
            out.found[need.key] = Found(
                None,
                [rows[0]["id"]],
                [_citation(rows[0])],
                "approved" if rows[0]["status"] == "approved" else "pending",
            )
            continue
        if not values:
            out.found[need.key] = Found(None, [], [], "missing")
            continue
        if need.pick == "one" and len(values) > 1:
            value, status = None, "ambiguous"
        else:
            value = values[-1] if need.pick in ("max", "one") else values[0]
            status = "approved" if rows[0]["status"] == "approved" else "pending"
        used = [r for r in rows if r["value_numeric"] is not None and float(r["value_numeric"]) == value] or rows
        out.found[need.key] = Found(
            value,
            [r["id"] for r in used],
            [_citation(r) for r in used],
            status,
        )
    return out


# R1 variation zones (LAMC Tables 12.08 C.5.(b)-(d)): one table column per zone, one row per lot-size band.
VARIATION_TABLE = {"V": "LAMC 12.08 C.5(b)", "F": "LAMC 12.08 C.5(c)", "R": "LAMC 12.08 C.5(d)"}
LOT_BANDS = [
    (6000, "Up to 6,000"),
    (7000, "6,001 to 7,000"),
    (8000, "7,001 to 8,000"),
    (9000, "8,001 to 9,000"),
    (10000, "9,001 to 10,000"),
    (float("inf"), "Over 10,000"),
]


def lot_band(lot_area: float) -> str:
    return next(label for top, label in LOT_BANDS if lot_area <= top)


def variation_needs(zone: str, lot_area: float) -> list[Need]:
    """Inputs for one variation zone: its floor-area ratio and lot coverage for this lot size, and its mass rows."""
    sec = VARIATION_TABLE[zone[2]]
    band = f"Lot {lot_band(lot_area)} sq ft"
    needs = [
        Need("ratio", sec, "rfa_ratio", applies=zone, condition_has=band),
        Need("coverage_pct", sec, "lot_coverage_max_pct", applies=zone, condition_has=band),
    ]
    if zone[2] == "V":
        needs += [
            Need("height_ft", sec, "height_max_ft", applies=zone),
            Need("plane_ft", sec, "encroachment_plane_origin_ft", applies=zone),
        ]
    else:
        for mass in ("front", "rear"):
            needs += [
                Need(f"{mass}_height_ft", sec, "height_max_ft", applies=zone, condition_has=f"{mass} mass"),
                Need(
                    f"{mass}_plane_ft", sec, "encroachment_plane_origin_ft", applies=zone, condition_has=f"{mass} mass"
                ),
            ]
        other = "rear" if zone[2] == "F" else "front"
        needs.append(
            Need(f"{other}_depth_ft", sec, "mass_envelope_depth_ft", applies=zone, condition_has=f"{other} mass")
        )
    return needs


# Hillside Area (LAMC 12.21 C.10): Table C.10-4 heights by height district row, C.10-2a/2b ratios by slope band.
HILLSIDE_BANDS = ["0 - 14.99", "15 - 29.99", "30 - 44.99", "45 - 59.99", "60 - 99.99", "100 +"]


def hillside_hd_row(height_district: str | None) -> str | None:
    hd = (height_district or "").upper()
    if hd.endswith("SS"):
        return "1SS"
    if hd.endswith("XL"):
        return "1XL"
    if hd in ("1", "1L", "1VL"):
        return "1, 1L, & 1VL"
    return None


def hillside_needs(zone: str, hd_row: str) -> list[Need]:
    """Heights use the R1 column (R1H lots follow the R1 Hillside standards); ratios use the zone's own column."""
    sec_b, sec_d = "LAMC 12.21 C.10(b)", "LAMC 12.21 C.10(d)"
    needs = [
        Need(
            "max_ft", sec_d, "height_max_ft", applies="R1", condition_has=f"25% or greater; Height District {hd_row};"
        ),
        Need(
            "low_roof_ft",
            sec_d,
            "height_max_ft",
            applies="R1",
            condition_has=f"less than 25%; Height District {hd_row};",
        ),
        Need("min_pct", sec_b, "rfa_guaranteed_min_pct", applies="R1"),
        Need("coverage_pct", "LAMC 12.21 C.10(e)", "lot_coverage_max_pct", "6 feet above natural ground"),
        Need("coverage_small_pct", "LAMC 12.21 C.10(e)", "lot_coverage_max_pct", "substandard as to width"),
    ]
    needs += [
        Need(f"band_{k}", sec_b, "rfa_ratio", applies=zone, condition_has=f"slope band {b}%")
        for k, b in enumerate(HILLSIDE_BANDS)
    ]
    return needs


# R2 Two-Family Zone (LAMC 12.09). Yards are the R1 yards (12.09 C.1-C.3 refer to 12.08 C.1-C.3).
# LA County Title 22, Zone R-1 (unincorporated County). Table 22.18.040-A gives R-A, R-1 and R-2 one shared row.
RULES |= {
    "COUNTY_R1_YARDS": [
        Need("front", "LACC 22.18.040 A", "front_yard_min_ft", applies="R-1"),
        Need("side", "LACC 22.18.040 A", "side_yard_min_ft", applies="R-1"),
        Need("rear", "LACC 22.18.040 A", "rear_yard_min_ft", applies="R-1"),
        Need("corner_side", "LACC 22.18.040 A", "corner_side_yard_min_ft", applies="R-1"),
    ],
    # The County's own ADU rules (Ord. 2025-0029); HCD found parts of it out of line with state law.
    "COUNTY_ADU": [
        Need("max_sqft", "LACC 22.140.640 G.1.a", "adu_max_floor_area_sqft", "1,200 square feet"),
        Need("height_ft", "LACC 22.140.640 G.1.b", "adu_height_max_ft", "shall be 25 feet"),
        Need("setback_ft", "LACC 22.140.640 G.1.c", "adu_side_rear_setback_ft", "four feet from the rear"),
        Need("counts", "LACC 22.140.640 E", "adu_count_max", "attached to or within a single", numeric=False),
        Need("no_parking", "LACC 22.140.640 G.1.d", "adu_parking_required", "outside of a V", numeric=False),
    ],
    "COUNTY_ADU_FIRE": [
        Need("two_access", "LACC 22.140.640 C", "adu_allowed", "two distinct means", numeric=False),
        Need("highway_front", "LACC 22.140.640 C", "adu_allowed", "single", numeric=False),
    ],
    "COUNTY_REVERSED_CORNER": [
        Need("side_ft", "LACC 22.18.040 A", "other", applies="R-1", condition_has="Reversed Corner"),
    ],
    "COUNTY_NARROW_LOT": [
        Need("pct", "LACC 22.110.080 C", "side_yard_pct_lot_width", "less than 50 feet"),
        Need("min_ft", "LACC 22.110.080 C", "side_yard_min_ft", "less than 50 feet"),
    ],
    "COUNTY_SHALLOW_LOT": [
        Need("pct", "LACC 22.110.080 D", "rear_yard_pct_lot_depth", "less than 75 feet"),
        Need("min_ft", "LACC 22.110.080 D", "rear_yard_min_ft", "less than 75 feet"),
    ],
    "COUNTY_R1_HEIGHT": [Need("max_ft", "LACC 22.18.040 B", "height_max_ft", applies="R-1")],
    "COUNTY_LOT_AREA": [
        Need("default", "LACC 22.110.130 A", "lot_area_min_sqft", "R-1-5000", numeric=False),
        Need("numbered", "LACC 22.110.130 A", "lot_area_min_sqft", "net area of the number", numeric=False),
    ],
}

RULES |= {
    "R2_USE": [Need("rule", "LAMC 12.09 A.2", "dwelling_units_max", "two single", numeric=False)],
    "R2_YARDS": [
        Need("front", "LAMC 12.09 C.1", "front_yard_min_ft", "Same as required", numeric=False),
        Need("side", "LAMC 12.09 C.2", "side_yard_min_ft", "Same as required", numeric=False),
        Need("rear", "LAMC 12.09 C.3", "rear_yard_min_ft", "Same as required", numeric=False),
    ],
    "R2_DENSITY": [
        Need("per_unit_sqft", "LAMC 12.09 C.4", "lot_area_per_unit_sqft", "minimum lot area per dwelling unit"),
        Need("two_family_min_sqft", "LAMC 12.09 C.4", "lot_area_min_sqft", "In no case"),
    ],
    "R2_LOT_MINIMUMS": [
        Need("area_sqft", "LAMC 12.09 C.4", "lot_area_min_sqft", "Every lot shall have a minimum width"),
        Need("width_ft", "LAMC 12.09 C.4", "lot_width_min_ft", "Every lot shall have a minimum width"),
    ],
    "R2_HEIGHT": [Need("max_ft", "LAMC 12.21.1", "height_max_ft", "In the R2 Zone, no Building")],
    "R2_FLOOR_AREA": [
        Need("buildable_x", "LAMC 12.21.1 A.1", "other", "all other zones, except the RA, RE, RS, and R1 Zones")
    ],
    # RE Residential Estate Zone (LAMC 12.07.01), off the Hillside Area and Coastal Zone.
    "RE_FRONT_YARD": [
        Need("pct", "LAMC 12.07.01 C.1", "front_yard_pct_lot_depth", "20% of the depth"),
        Need("max_ft", "LAMC 12.07.01 C.1", "front_yard_max_ft", "20% of the depth"),
    ],
    "RE_REAR_YARD": [
        Need("pct", "LAMC 12.07.01 C.3", "rear_yard_pct_lot_depth", "25% of the depth"),
        Need("max_ft", "LAMC 12.07.01 C.3", "other", "rear yard need not exceed 25 feet"),
    ],
    "GUEST_HOUSE_RE": [
        Need("min_lot_sqft", "LAMC 12.07.01 A.6", "alq_min_lot_area_sqft"),
        Need("stories", "LAMC 12.07.01 A.6", "stories_max", "not exceeding two stories"),
    ],
}


def re_needs(zone: str) -> dict[str, list[Need]]:
    """Side yard, height, lot minimum and floor area inputs for one RE designation (RE9, RE11, RE15, RE20, RE40)."""
    sec = "LAMC 12.07.01 C.2"
    common = [
        Need("per_story_ft", sec, "side_yard_extra_per_story_ft", "more than two- stories"),
        Need("in_lieu", sec, "other", "In lieu of the additional side yard requirement", numeric=False),
    ]
    if zone in ("RE9", "RE11"):
        side = [
            Need("base_ft", sec, "side_yard_min_ft", "Notwithstanding the above paragraph"),
            Need("narrow_pct", sec, "side_yard_pct_lot_width", "Notwithstanding the above paragraph"),
        ]
    elif zone == "RE15":
        side = [
            Need("pct", sec, "side_yard_pct_lot_width", "designated RE15"),
            Need("min_ft", sec, "side_yard_min_ft", "designated RE15"),
            Need("max_ft", sec, "other", "designated RE15"),
        ]
    else:
        side = [Need("base_ft", sec, "side_yard_min_ft", "RE20 or RE40")]
    height_quote = "R1, RS, or RE9" if zone == "RE9" else "RE11, RE15, RE20, RE 40"
    rfa = (
        [Need("pct", "LAMC 12.07.01 C.5", "rfa_max_pct_lot_area", "less than 15,000 square feet")]
        if zone in ("RE9", "RE11")
        else [Need("pct", "LAMC 12.07.01 C.5", "rfa_max_pct_lot_area", "RE15, RE20 and RE40")]
    )
    return {
        "side": side + common,
        "height": [
            Need("max_ft", "LAMC 12.21.1", "height_max_ft", height_quote, pick="max"),
            Need("low_roof_ft", "LAMC 12.21.1", "height_max_ft", height_quote, pick="min"),
        ],
        "lot": [
            Need("area_sqft", "LAMC 12.07.01 C.4", "lot_area_min_sqft", applies=zone),
            Need("width_ft", "LAMC 12.07.01 C.4", "lot_width_min_ft", applies=zone),
        ],
        "rfa": rfa,
    }
