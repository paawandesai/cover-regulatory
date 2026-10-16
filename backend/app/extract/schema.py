"""What the extraction model may return. Every field except the quote may be null, and an empty list is a
valid answer. There is deliberately no confidence field: confidence is computed, never asked of the model."""

from typing import Literal

from pydantic import BaseModel, Field

RuleFamily = Literal["r1_envelope", "guest_house", "adu_state", "adu_local", "jadu", "flag", "other"]
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
    "rfa_bonus_pct": "percent",
    "lot_coverage_max_pct": "percent",
    "rfa_parking_exempt_sqft": "sqft",
    "rfa_parking_front_setback_ft": "ft",
    "rfa_accessory_exempt_sqft": "sqft",
    "rfa_double_count_ceiling_ft": "ft",
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
