"""Deterministic checks on model-extracted fragments. A fragment that fails any check is stored as
'invalid' with the reason, so a reviewer sees it but no assessment can ever use it."""

import re
from dataclasses import dataclass

from app.extract.schema import PARAMETERS, Fragment

_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "sixteen": 16,
    "eighteen": 18,
    "twenty": 20,
    "twenty-five": 25,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
}
_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": "-"})


@dataclass
class Checked:
    fragment: Fragment
    validation: str  # "ok" or a reason
    quote_start: int | None
    quote_end: int | None


def locate_quote(quote: str, text: str) -> tuple[int, int] | None:
    """Offsets of `quote` in `text`, ignoring differences in whitespace and curly vs straight quotes."""
    words = quote.translate(_QUOTES).split()
    if len(words) < 3:
        return None
    pattern = r"\s+".join(re.escape(w) for w in words)
    m = re.search(pattern, text.translate(_QUOTES))
    return (m.start(), m.end()) if m else None


def _number_forms(v: float) -> set[str]:
    forms = {f"{v:g}"}
    if v == int(v):
        forms |= {str(int(v)), f"{int(v):,}"}
    return forms


def number_in_quote(v: float, quote: str) -> bool:
    q = quote.translate(_QUOTES).lower()
    if any(re.search(r"(?<![\d.,])" + re.escape(f) + r"(?![\d]|[.,]\d)", q) for f in _number_forms(v)):
        return True
    return any(n == v and re.search(r"\b" + w + r"\b", q) for w, n in _WORDS.items())


def check(fragment: Fragment, chunks: dict[str, str]) -> Checked:
    text = chunks.get(fragment.chunk_id)
    if text is None:
        return Checked(fragment, "unknown_chunk_id", None, None)
    span = locate_quote(fragment.source_quote, text)
    if span is None:
        return Checked(fragment, "quote_not_in_chunk", None, None)
    if fragment.parameter not in PARAMETERS:
        return Checked(fragment, "unknown_parameter", *span)
    expected_unit = PARAMETERS[fragment.parameter]
    if fragment.value_numeric is not None and fragment.parameter == "other":
        # Unlisted rules are for reading only; the number still has to be in the quote.
        if not number_in_quote(fragment.value_numeric, fragment.source_quote):
            return Checked(fragment, "value_not_in_quote", *span)
    elif fragment.value_numeric is not None:
        if expected_unit in ("boolean", "text"):
            return Checked(fragment, "numeric_value_for_non_numeric_parameter", *span)
        if fragment.unit != expected_unit:
            return Checked(fragment, f"unit_mismatch(expected {expected_unit})", *span)
        if not number_in_quote(fragment.value_numeric, fragment.source_quote):
            return Checked(fragment, "value_not_in_quote", *span)
    elif expected_unit not in ("boolean", "text") and not fragment.value_text:
        return Checked(fragment, "no_value", *span)
    return Checked(fragment, "ok", *span)
