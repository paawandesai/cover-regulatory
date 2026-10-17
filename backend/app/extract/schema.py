"""What the extraction model may return. Every field except the quote may be null, and an empty list is a
valid answer. There is deliberately no confidence field: confidence is computed, never asked of the model."""

from typing import Literal

from pydantic import BaseModel, Field

RuleFamily = Literal[
    "r1_envelope",
    "r2_envelope",
    "re_envelope",
    "guest_house",
    "adu_state",
    "adu_local",
    "jadu",
    "sb9",
    "fire_rebuild",
    "flag",
    "other",
]
Unit = Literal["ft", "sqft", "percent", "ratio", "stories", "count", "days", "boolean", "text"]

# The parameters the rule engine knows how to apply. Anything else is extracted as "other" for a reviewer
# to read, and the engine ignores it.
PARAMETERS: dict[str, Unit] = {
    # R1 envelope (LAMC 12.08 C, 12.21 C, 12.21.1)
    "front_yard_min_ft": "ft",
    "front_yard_max_ft": "ft",
    "front_yard_pct_lot_depth": "percent",
    "side_yard_min_ft": "ft",
    "side_yard_pct_lot_width": "percent",
    "side_yard_extra_per_story_ft": "ft",
    "rear_yard_min_ft": "ft",
    "rear_yard_pct_lot_depth": "percent",
    "lot_area_min_sqft": "sqft",
    "lot_width_min_ft": "ft",
    "height_max_ft": "ft",
    "stories_max": "stories",
    "rfa_ratio": "ratio",
    "rfa_max_pct_lot_area": "percent",
    "rfa_bonus_pct": "percent",
    "lot_coverage_max_pct": "percent",
    "rfa_parking_exempt_sqft": "sqft",
    "rfa_parking_front_setback_ft": "ft",
    "rfa_accessory_exempt_sqft": "sqft",
    "rfa_double_count_ceiling_ft": "ft",
    "encroachment_plane_origin_ft": "ft",
    "mass_envelope_depth_ft": "ft",
    "rfa_guaranteed_min_pct": "percent",
    # Guest house = accessory living quarters (no kitchen)
    "alq_allowed": "boolean",
    "alq_min_lot_area_sqft": "sqft",
    "alq_kitchen_prohibited": "boolean",
    "alq_max_floor_area_sqft": "sqft",
    # ADU / JADU
    "adu_allowed": "boolean",
    "adu_count_max": "count",
    "adu_max_floor_area_sqft": "sqft",
    "adu_max_floor_area_pct_primary": "percent",
    "adu_min_floor_area_sqft": "sqft",
    "adu_side_rear_setback_ft": "ft",
    "adu_height_max_ft": "ft",
    "adu_parking_required": "boolean",
    "adu_owner_occupancy_required": "boolean",
    "adu_approval_days": "days",
    "jadu_max_floor_area_sqft": "sqft",
    "jadu_count_max": "count",
    # SB 9 (Gov. Code 65852.21 two-unit development, 66411.7 urban lot split)
    "sb9_lot_split_min_pct": "percent",
    "sb9_lot_split_min_sqft": "sqft",
    "sb9_units_per_lot_max": "count",
    "sb9_unit_min_floor_area_sqft": "sqft",
    "sb9_side_rear_setback_ft": "ft",
    # Mayor's emergency orders after the January 2025 fires
    "rebuild_max_pct_prior": "percent",
    "rebuild_bluff_setback_ft": "ft",
    "sb9_suspended": "boolean",
    "dwelling_units_max": "count",
    "lot_area_per_unit_sqft": "sqft",
    "other": "text",
}


class Fragment(BaseModel):
    chunk_id: str = Field(description="The chunk_id of the document the quote comes from, copied exactly.")
    rule_family: RuleFamily
    parameter: str = Field(description="One of the listed parameter names, or 'other'.")
    applies_to: list[str] = Field(description="Zones or building types the rule applies to, as the text names them.")
    conditions: str | None = Field(description="Conditions or exceptions stated in the text, or null.")
    value_numeric: float | None = Field(description="The number exactly as the text states it, or null.")
    unit: Unit | None
    value_text: str | None = Field(description="Non-numeric value or formula in the text's words, or null.")
    source_quote: str = Field(description="A verbatim span of the document text that states this rule.")


class Extraction(BaseModel):
    fragments: list[Fragment]
