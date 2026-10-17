"""Deterministic reader for the R1 variation zone tables (LAMC Tables 12.08 C.5.(b)-(d)).

The saved code text flattens each table into one cell per line, which a model reads unreliably (it returned the
rows without per-zone values). The layout is regular, so this reads it by position instead: the four zone columns,
six lot-size rows of floor-area ratios with a lot coverage column, and the mass rows (height, encroachment plane
origin, envelope depth). Every cell becomes a candidate fragment whose quote is the whole row, checked like a model
fragment (quote in chunk, number in quote) and stored as 'pending' for review. No model is involved.

Run: uv run python -m app.extract.tables [--hillside | --ch1a-density]
"""

import re
import sys
from dataclasses import dataclass

from app.db.connection import connect
from app.extract.schema import Fragment
from app.extract.validate import check

READER = "table-reader"
VERSION = "table-v1"
SECTIONS = ("LAMC 12.08 C.5(b)", "LAMC 12.08 C.5(c)", "LAMC 12.08 C.5(d)")
_ZONE = re.compile(r"^R1[VFR][1-4]$")
_BAND = re.compile(r"(SF)$")
_RATIO = re.compile(r"^\.\d\d$")
_PCT = re.compile(r"^(\d+)%$")
_FEET = re.compile(r"^(\d+)'$")
_DASH = {"–", "-", "—"}
ROWS = {
    "Height of Building (max)": ("height_max_ft", "ft"),
    "Height of Mass (max)": ("height_max_ft", "ft"),
    "Encroachment Plane Origin Height": ("encroachment_plane_origin_ft", "ft"),
    "Front envelope depth, from front yard setback (min)": ("mass_envelope_depth_ft", "ft"),
    "Rear envelope depth, from rear yard setback (min)": ("mass_envelope_depth_ft", "ft"),
}


@dataclass
class Cell:
    text: str
    start: int
    end: int


def _cells(text: str) -> list[Cell]:
    return [Cell(m.group(0).strip(), m.start(), m.end()) for m in re.finditer(r"[^\n]+", text) if m.group(0).strip()]


def read_table(chunk_id: str, text: str) -> list[Fragment]:
    cells = _cells(text)
    zones_at = next((i for i in range(len(cells) - 3) if all(_ZONE.match(c.text) for c in cells[i : i + 4])), None)
    if zones_at is None:
        return []
    zones = [c.text for c in cells[zones_at : zones_at + 4]]
    out: list[Fragment] = []

    def frag(param, unit, zone, value, conditions, first, last):
        return Fragment(
            chunk_id=chunk_id,
            rule_family="r1_envelope",
            parameter=param,
            applies_to=[zone],
            conditions=conditions,
            value_numeric=value,
            unit=unit,
            value_text=None,
            source_quote=text[cells[first].start : cells[last].end],
        )

    mass = None
    i = zones_at + 4
    while i < len(cells):
        t = cells[i].text
        if _BAND.search(t) and i + 5 < len(cells) and all(_RATIO.match(c.text) for c in cells[i + 1 : i + 5]):
            band = t.replace("SF", "sq ft")
            for k, z in enumerate(zones):
                out.append(frag("rfa_ratio", "ratio", z, float(cells[i + 1 + k].text), f"Lot {band}", i, i + 4))
            pct = _PCT.match(cells[i + 5].text)
            if pct:
                for z in zones:
                    out.append(frag("lot_coverage_max_pct", "percent", z, float(pct.group(1)), f"Lot {band}", i, i + 5))
            i += 6
            continue
        if t in ("Mass", "Front Mass", "Rear Mass"):
            mass = t.lower()
        elif t in ROWS and i + 4 < len(cells):
            param, unit = ROWS[t]
            vals = [c.text for c in cells[i + 1 : i + 5]]
            for z, v in zip(zones, vals, strict=True):
                m = _FEET.match(v)
                if m:
                    out.append(frag(param, unit, z, float(m.group(1)), f"{mass}: {t}" if mass else t, i, i + 4))
            i += 5
            continue
        i += 1
    return out


_SLOPE_BAND = re.compile(r"^(\d+ - \d+\.99|100 \+)$")
_DECIMAL = re.compile(r"^\d?\.\d\d$")
_INT = re.compile(r"^\d+$")
HILLSIDE_SECTIONS = ("LAMC 12.21 C.10(b)", "LAMC 12.21 C.10(d)")
HD_ROWS = ("1, 1L, & 1VL", "1XL", "1SS")


def _table_name(cells: list[Cell], i: int) -> str | None:
    return next((c.text for c in reversed(cells[:i]) if c.text.startswith("Table 12.21")), None)


def read_hillside(chunk_id: str, text: str) -> list[Fragment]:
    """Tables 12.21 C.10-2a and -2b (floor-area ratio by slope band), C.10-3 (guaranteed minimum) and C.10-4
    (height by height district and roof slope)."""
    cells = _cells(text)
    out: list[Fragment] = []

    def frag(param, unit, zone, value, conditions, first, last):
        return Fragment(
            chunk_id=chunk_id,
            rule_family="r1_envelope",
            parameter=param,
            applies_to=[zone],
            conditions=conditions,
            value_numeric=value,
            unit=unit,
            value_text=None,
            source_quote=text[cells[first].start : cells[last].end],
        )

    for i, c in enumerate(cells):
        if c.text == "Slope Bands (%)":
            j = i + 1
            zones = []
            while j < len(cells) and re.match(r"^R[A-Z0-9]+$", cells[j].text):
                zones.append(cells[j].text)
                j += 1
            name = _table_name(cells, i)
            while zones and j + len(zones) < len(cells) and _SLOPE_BAND.match(cells[j].text):
                vals = cells[j + 1 : j + 1 + len(zones)]
                if not all(_DECIMAL.match(v.text) for v in vals):
                    break
                for z, v in zip(zones, vals, strict=True):
                    cond = f"Hillside Area; slope band {cells[j].text}%; {name}"
                    out.append(frag("rfa_ratio", "ratio", z, float(v.text), cond, j, j + len(zones)))
                j += len(zones) + 1
        elif c.text == "Percentage of Lot Size":
            j = i + 1
            while j + 1 < len(cells) and re.match(r"^R[A-Z0-9]+$", cells[j].text) and _PCT.match(cells[j + 1].text):
                pct = float(_PCT.match(cells[j + 1].text).group(1))
                cond = f"Hillside Area guaranteed minimum; {_table_name(cells, i)}"
                # The quote runs from the column headings so it is long enough to locate.
                out.append(frag("rfa_guaranteed_min_pct", "percent", cells[j].text, pct, cond, i - 1, j + 1))
                j += 2
        elif c.text == "Height Districts":
            j = i + 1
            zones = []
            while j < len(cells) and re.match(r"^R[A-Z0-9]+$", cells[j].text):
                zones.append(cells[j].text)
                j += 1
            roof = None
            while j < len(cells):
                t = cells[j].text
                if t.startswith("When the roof"):
                    roof = "roof slope 25% or greater" if "25% or greater" in t else "roof slope less than 25%"
                    j += 1
                elif t in HD_ROWS and roof and j + len(zones) < len(cells):
                    vals = cells[j + 1 : j + 1 + len(zones)]
                    if not all(_INT.match(v.text) for v in vals):
                        break
                    for z, v in zip(zones, vals, strict=True):
                        cond = f"Hillside Area; {roof}; Height District {t}; Table 12.21 C.10-4"
                        out.append(frag("height_max_ft", "ft", z, float(v.text), cond, j, j + len(zones)))
                    j += len(zones) + 1
                else:
                    break
    return out


DENSITY_SECTIONS = ("Ch. 1A Div. 6B.1", "Ch. 1A Div. 6B.2")
_LOT_LIMITED = re.compile(r"^(\d{1,2})L (\d{1,2})$")
_AREA_BASED = re.compile(r"^(\d{1,2}) (\d{3,4}) (\d{3,4}) (Applicable|Market-contingent|As Mapped)$")


def read_density(chunk_id: str, text: str) -> list[Fragment]:
    """Chapter 1A Div. 6B.1 (dwelling units per lot in 1L-4L) and Div. 6B.2 (lot area per household dwelling unit in
    the numbered districts). "FA" and "N" rows hold words, not numbers, and are left to the engine's cited text."""
    out: list[Fragment] = []
    cells = _cells(text)
    head = next((c for c in cells if c.text == "Density District Per Lot (max)"), None)
    for c in cells:
        if m := _LOT_LIMITED.match(c.text):
            param, district, value = "units_per_lot_max", f"{m.group(1)}L", float(m.group(2))
            unit, cond = "count", "Lot-Limited Density District (Div. 6B.1)"
        elif m := _AREA_BASED.match(c.text):
            param, district, value = "lot_area_per_unit_sqft", m.group(1), float(m.group(2))
            unit, cond = "sqft", "Lot Area-Based Density District (Div. 6B.2); household dwelling unit"
        else:
            continue
        out.append(
            Fragment(
                chunk_id=chunk_id,
                rule_family="ch1a_density",
                parameter=param,
                applies_to=[district],
                conditions=cond,
                value_numeric=value,
                unit=unit,
                value_text=None,
                # A row like "2L 2" is too short to locate on its own, so the quote starts at the column heading.
                source_quote=text[head.start if param == "units_per_lot_max" and head else c.start : c.end],
            )
        )
    return out


def main() -> None:
    with connect() as conn:
        hillside = "--hillside" in sys.argv
        density = "--ch1a-density" in sys.argv
        sections = DENSITY_SECTIONS if density else HILLSIDE_SECTIONS if hillside else SECTIONS
        chunks = conn.execute(
            "SELECT id, text, content_hash FROM reg_chunk WHERE section_id = ANY(%s) AND NOT mock ORDER BY id",
            (list(sections),),
        ).fetchall()
        reader = read_density if density else read_hillside if hillside else read_table
        run_id = conn.execute(
            """INSERT INTO extraction_run (model_id, served_model, prompt_version, chunk_ids, status, finished_at)
               VALUES (%s, %s, %s, %s, 'ok', now()) RETURNING id""",
            (READER, READER, VERSION, [c["id"] for c in chunks]),
        ).fetchone()["id"]
        counts = {"ok": 0, "invalid": 0}
        for c in chunks:
            for f in reader(c["id"], c["text"]):
                ck = check(f, {c["id"]: c["text"]})
                ok = ck.validation == "ok"
                counts["ok" if ok else "invalid"] += 1
                conn.execute(
                    """INSERT INTO rule_fragment (run_id, chunk_id, chunk_hash, rule_family, parameter, applies_to,
                           conditions, value_numeric, unit, value_text, source_quote, quote_start, quote_end,
                           validation, status)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        run_id,
                        f.chunk_id,
                        c["content_hash"],
                        f.rule_family,
                        f.parameter,
                        f.applies_to,
                        f.conditions,
                        f.value_numeric,
                        f.unit,
                        None,
                        f.source_quote,
                        ck.quote_start,
                        ck.quote_end,
                        ck.validation,
                        "pending" if ok else "invalid",
                    ),
                )
        conn.commit()
    print({"run_id": run_id, **counts})


if __name__ == "__main__":
    main()
