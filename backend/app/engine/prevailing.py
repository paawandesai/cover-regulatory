"""Prevailing front yard and key-lot estimates (LAMC 12.08 C.1), from neighbouring parcels and building outlines.

Everything here rests on approximate inputs: County parcel outlines and machine-learned building outlines. Results
are labeled "Approximate" and say which lots were counted, so a reviewer can check them on a survey.

Method (EPSG:2229, US feet):
  1. The street line is the subject lot's front side, extended along the street.
  2. The block frontage is the run of parcels whose front edge sits on that line (within 20 ft), walking out from
     the subject lot until a gap of more than 15 ft (a cross street, or the edge of the loaded data). At most
     600 ft each way.
  3. A lot's front yard is the distance from its front edge to its nearest building, ignoring buildings entirely
     on the rear half (12.08 C.1 says not to count them), outlines under 150 sq ft, the subject lot's own
     buildings (they are what is being designed), lots in a C or M zone, key lots and reversed corner lots.
  4. Every set of developed lots whose front yards are within 10 ft of each other and which together make up 40%
     or more of the frontage is a candidate; the shallowest average wins, capped at 40 ft.
"""

import math
from dataclasses import dataclass

from shapely import wkb

from app.engine.geometry import _TO_FT, LotFrame, lot_frame, transform

REACH_FT = 600.0
ON_LINE_FT = 20.0
GAP_FT = 15.0
STREET_GAP_FT = 40.0
MIN_BUILDING_SQFT = 150.0
SPREAD_FT = 10.0  # "vary in depth by not more than ten feet"
SHARE = 0.40  # "comprise 40% or more of the frontage"


@dataclass
class Lot:
    apn: str
    a0: float  # extent along the street
    a1: float
    front: float  # offset of its front edge from the street line (inward positive)
    depth: float  # extent away from the street
    zone: str | None
    yard: float | None = None  # front yard to the nearest counted building; None if not developed
    excluded: str | None = None  # why its buildings are not counted

    @property
    def frontage(self) -> float:
        return self.a1 - self.a0


def _axes(frame: LotFrame) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    a = math.radians(frame.angle_deg)
    u = (math.cos(a), math.sin(a))
    fx, fy = frame.front_mid
    n = (-u[1], u[0])
    if (frame.origin[0] - fx) * n[0] + (frame.origin[1] - fy) * n[1] < 0:
        n = (-n[0], -n[1])
    return (fx, fy), u, n


def _proj(geom, o, u, n) -> tuple[list[float], list[float]]:
    pts = (
        list(geom.exterior.coords) if hasattr(geom, "exterior") else [c for g in geom.geoms for c in g.exterior.coords]
    )
    return (
        [(x - o[0]) * u[0] + (y - o[1]) * u[1] for x, y in pts],
        [(x - o[0]) * n[0] + (y - o[1]) * n[1] for x, y in pts],
    )


def block_face(conn, apn: str, frame: LotFrame) -> tuple[list[Lot], int]:
    """The lots on the subject's side of the street, in order along it, and the subject's index."""
    o, u, n = _axes(frame)
    rows = conn.execute(
        """SELECT p.apn, ST_AsBinary(p.geom) AS g,
                  (SELECT z.zone_string FROM zoning z WHERE ST_Intersects(z.geom, ST_PointOnSurface(p.geom)) LIMIT 1)
                      AS zone
           FROM parcel p
           WHERE p.geom && ST_Transform(ST_Expand(ST_SetSRID(ST_Point(%s, %s), 2229), %s), 4326)""",
        (o[0], o[1], REACH_FT + 200),
    ).fetchall()
    lots = []
    for r in rows:
        g = transform(_TO_FT, wkb.loads(bytes(r["g"])))
        g = max(getattr(g, "geoms", [g]), key=lambda x: x.area)
        al, de = _proj(g, o, u, n)
        front, back = min(de), max(de)
        if r["apn"] != apn and (abs(front) > ON_LINE_FT or back - front < 40):
            continue
        if max(al) < -REACH_FT or min(al) > REACH_FT:
            continue
        lots.append(Lot(r["apn"], min(al), max(al), front, back - front, r["zone"]))
    lots.sort(key=lambda lot: lot.a0)
    i = next((k for k, lot in enumerate(lots) if lot.apn == apn), None)
    if i is None:
        return [], 0
    lo = hi = i
    while lo > 0 and lots[lo - 1].a1 >= lots[lo].a0 - GAP_FT:
        lo -= 1
    while hi < len(lots) - 1 and lots[hi + 1].a0 <= max(lot.a1 for lot in lots[lo : hi + 1]) + GAP_FT:
        hi += 1
    return lots[lo : hi + 1], i - lo


def _yards(conn, face: list[Lot], subject: int, frame: LotFrame) -> None:
    o, u, n = _axes(frame)
    counted = []
    for k, lot in enumerate(face):
        zone = (lot.zone or "").lstrip("[](QT)").upper()
        if k == subject:
            lot.excluded = "the lot being assessed"
        elif zone.startswith(("C", "M")) and not zone.startswith("CR"):
            lot.excluded = "C or M zone"
        else:
            counted.append(lot)
    rows = conn.execute(
        """SELECT p.apn, ST_AsBinary(b.geom) AS g FROM parcel p JOIN building_footprint_odbl b ON ST_Intersects(p.geom, b.geom)
           WHERE p.apn = ANY(%s) AND ST_Area(ST_Intersection(p.geom, b.geom)) > 0.5 * ST_Area(b.geom)""",
        ([lot.apn for lot in counted],),
    ).fetchall()
    by_apn: dict[str, list] = {}
    for r in rows:
        by_apn.setdefault(r["apn"], []).append(r["g"])
    for lot in counted:
        best = None
        for g in by_apn.get(lot.apn, []):
            b = transform(_TO_FT, wkb.loads(bytes(g)))
            if b.area < MIN_BUILDING_SQFT:
                continue
            _, de = _proj(b, o, u, n)
            near = min(de) - lot.front
            if near >= lot.depth / 2:
                continue  # entirely on the rear half
            best = near if best is None else min(best, near)
        lot.yard = max(round(best, 1), 0.0) if best is not None else None


def _reversed_corner(lot: Lot, frame: LotFrame) -> bool:
    """A corner lot whose front faces the cross street: its own front side runs across this street's line."""
    other = lot_frame(lot.apn)
    if other is None or not other.corner or other.front_side is None:
        return False
    return abs(math.cos(math.radians(other.angle_deg - frame.angle_deg))) < 0.5


def _mark_corners(face: list[Lot], subject: int, frame: LotFrame) -> int | None:
    """Mark reversed corner lots at the ends of the run and the key lots beside them. Returns the index of the
    subject's reversed-corner neighbour when the subject is itself a key lot."""
    neighbour = None
    for end, inner in ((0, 1), (len(face) - 1, len(face) - 2)):
        if end == subject or not (0 <= inner < len(face)) or not _reversed_corner(face[end], frame):
            continue
        face[end].excluded = face[end].excluded or "reversed corner lot (fronts the cross street)"
        face[end].yard = None
        if inner == subject:
            neighbour = end
        else:
            face[inner].excluded = face[inner].excluded or "key lot"
            face[inner].yard = None
    return neighbour


def _key_inputs(face: list[Lot], subject: int, corner: int) -> dict | None:
    """The adjoining interior lot (on the side away from the reversed corner lot) and the corner lot itself."""
    inner = subject + (1 if corner < subject else -1)
    if not 0 <= inner < len(face):
        return None
    cf = lot_frame(face[corner].apn)
    return {
        "interior_apn": face[inner].apn,
        "interior_depth_ft": round(face[inner].depth, 1),
        "corner_apn": face[corner].apn,
        "corner_width_ft": round(cf.width_ft, 1) if cf else None,
    }


def shallowest_group(developed: list[Lot], total: float) -> dict | None:
    """Of the groups of developed lots whose front yards are within 10 ft of each other and that make up 40% or more
    of the frontage, the one with the shallowest average front yard. Each group is every lot within 10 ft of its
    shallowest member ("all of the developed lots which have front yards that vary ... by not more than ten feet")."""
    developed = sorted(developed, key=lambda lot: lot.yard)
    best = None
    for i, first in enumerate(developed):
        group = [lot for lot in developed[i:] if lot.yard - first.yard <= SPREAD_FT]
        share = sum(lot.frontage for lot in group) / total if total else 0
        if share >= SHARE:
            avg = sum(lot.yard for lot in group) / len(group)
            if best is None or avg < best["average_ft"]:
                best = {"average_ft": round(avg, 1), "lots": [lot.apn for lot in group], "share": round(share, 2)}
    return best


def prevailing(conn, apn: str, frame: LotFrame, cap_ft: float) -> dict | None:
    if frame is None or frame.front_side is None or frame.front_mid is None:
        return None
    face, subject = block_face(conn, apn, frame)
    if len(face) < 3:
        return None
    _yards(conn, face, subject, frame)
    key_neighbour = _mark_corners(face, subject, frame)
    total = sum(lot.frontage for lot in face)
    developed = sorted((lot for lot in face if lot.yard is not None), key=lambda lot: lot.yard)
    best = shallowest_group(developed, total)
    return {
        "frontage_ft": round(total),
        "lots": len(face),
        "developed": len(developed),
        "excluded": [{"apn": lot.apn, "why": lot.excluded} for lot in face if lot.excluded],
        "yards_ft": [lot.yard for lot in developed],
        "combination": best,
        "value_ft": min(best["average_ft"], cap_ft) if best else None,
        "key_lot": key_neighbour is not None,
        "key": _key_inputs(face, subject, key_neighbour) if key_neighbour is not None else None,
        "subject_frontage_ft": round(face[subject].frontage),
    }
