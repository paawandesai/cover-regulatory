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
    "RFA_EXEMPTIONS": [
        Need("double_ceiling_ft", "LAMC 12.03(b)", "rfa_double_count_ceiling_ft", "greater than 14 feet"),
        Need("parking_max_sqft", "LAMC 12.03(b)", "rfa_parking_exempt_sqft", "200 square feet per parking space"),
        Need("parking_fallback_sqft", "LAMC 12.03(b)", "rfa_parking_exempt_sqft", "only 200 square feet"),
        Need("parking_front_ft", "LAMC 12.03(b)", "rfa_parking_front_setback_ft", "rear half of the Lot"),
        Need("parking_through_ft", "LAMC 12.03(b)", "rfa_parking_front_setback_ft", "Through Lot"),
        Need("accessory_each_sqft", "LAMC 12.03(c)", "rfa_accessory_exempt_sqft", "Detached Accessory", pick="min"),
        Need("accessory_total_sqft", "LAMC 12.03(c)", "rfa_accessory_exempt_sqft", "Detached Accessory", pick="max"),
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


def load(rule_id: str, conn=None) -> RuleInputs:
    if conn is None:
        with connect() as c:
            return load(rule_id, c)
    out = RuleInputs(rule_id)
    for need in RULES[rule_id]:
        clause, arg = _section_clause(need.section)
        rows = conn.execute(
            f"""SELECT f.id, f.status, f.reviewed_by, f.value_numeric, f.source_quote, f.quote_start, f.quote_end, f.chunk_id,
                       c.section_id, c.code_chapter, c.source_url, c.page_start, c.retrieved_at::text AS retrieved_at
                FROM rule_fragment f JOIN reg_chunk c ON c.id = f.chunk_id
                WHERE {clause} AND f.parameter = %s AND f.status IN ('approved', 'pending')
                  AND f.validation = 'ok' AND f.chunk_hash = c.content_hash AND NOT c.mock
                  AND (%s::text IS NULL OR f.source_quote ILIKE '%%' || %s || '%%')
                ORDER BY (f.status = 'approved') DESC, f.id""",
            (arg, need.parameter, need.quote_has, need.quote_has),
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
