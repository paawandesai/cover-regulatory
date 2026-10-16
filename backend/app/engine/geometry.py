"""Illustrative lot geometry: width, depth, which side faces the street, and a setback envelope.

Everything here is approximate and labeled "illustrative, not survey-grade". Lot lines come from the County
parcel layer, which itself is "not for legal, engineering, or surveying use".

Method (deterministic, parcel data only):
  1. Project the parcel to EPSG:2229 (California State Plane V, US feet).
  2. Fit the minimum rotated rectangle; its short side is the width, its long side the depth.
  3. A rectangle side faces a street when the gap from its midpoint to the next parcel outward is street-wide.
     On a corner lot (streets on adjacent sides) the shorter street-facing side is taken as the front; with
     streets on opposite sides it is a through lot, with a front yard at each street end. A side with no parcel in reach is
     "unknown" (edge of the loaded data), and with no street side at all the front is not inferred.
  4. The envelope is the parcel minus the front, side and rear yards, measured in the rectangle's frame.
"""

import math
from dataclasses import dataclass

import numpy as np
import shapely
from pyproj import Transformer
from shapely import wkb
from shapely.affinity import rotate, translate
from shapely.geometry import Point, Polygon, box, mapping

from app.db.connection import connect

_FT = Transformer.from_crs(4326, 2229, always_xy=True)
_LL = Transformer.from_crs(2229, 4326, always_xy=True)
_TO_FT, _TO_LL = _FT.transform, _LL.transform


def transform(fn, geom):
    """Reproject a geometry with a pyproj transform function (vectorized over coordinates)."""
    return shapely.transform(geom, lambda c: np.column_stack(fn(c[:, 0], c[:, 1])))


# Along a ray out of each side's midpoint: a gap of 40 ft or more to the next parcel is read as a street
# (LA local streets are at least 50 ft of right-of-way), 10-40 ft as an alley, under 10 ft as a neighbour.
RAY_FT = 160.0
STREET_MIN_GAP_FT = 40.0
ALLEY_MIN_GAP_FT = 10.0


@dataclass
class LotFrame:
    lot_ft: Polygon
    width_ft: float
    depth_ft: float
    front_side: int | None  # index of the rectangle side taken as front, None if no street side was found
    street_sides: list[int]
    alley_sides: list[int]
    unknown_sides: list[int]
    corner: bool  # street on two adjacent sides
    through: bool  # street on two opposite sides
    angle_deg: float  # rotation that puts the front side along the x axis
    origin: tuple[float, float]
    front_mid: tuple[float, float] | None  # midpoint of the front side, EPSG:2229


def _sides(rect: Polygon) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    c = list(rect.exterior.coords)[:4]
    return [(c[i], c[(i + 1) % 4]) for i in range(4)]


def lot_frame(apn: str) -> LotFrame | None:
    with connect() as conn:
        row = conn.execute("SELECT ST_AsBinary(geom) AS g FROM parcel WHERE apn=%s", (apn,)).fetchone()
        if row is None:
            return None
        lot = transform(_TO_FT, wkb.loads(bytes(row["g"])))
        lot = max(getattr(lot, "geoms", [lot]), key=lambda g: g.area)
        rect = lot.minimum_rotated_rectangle
        sides = _sides(rect)
        center = rect.centroid
        street, alley, unknown = [], [], []
        for i, (a, b) in enumerate(sides):
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            vx, vy = mx - center.x, my - center.y
            n = math.hypot(vx, vy) or 1.0
            start = (mx + vx / n * 2, my + vy / n * 2)
            end = (mx + vx / n * RAY_FT, my + vy / n * RAY_FT)
            gap = conn.execute(
                """WITH ray AS (SELECT ST_SetSRID(ST_MakeLine(ST_Point(%s,%s), ST_Point(%s,%s)), 2229) AS g)
                   SELECT min(ST_Distance(ST_StartPoint(ray.g), ST_Intersection(ray.g, ST_Transform(p.geom, 2229))))
                          AS d
                   FROM ray, parcel p
                   WHERE p.apn <> %s AND ST_Intersects(p.geom, ST_Transform(ray.g, 4326))""",
                (*start, *end, apn),
            ).fetchone()["d"]
            if gap is None:
                unknown.append(i)  # nothing within reach: edge of the loaded data, or open land
            elif gap >= STREET_MIN_GAP_FT:
                street.append(i)
            elif gap >= ALLEY_MIN_GAP_FT:
                alley.append(i)
    lengths = [math.dist(a, b) for a, b in sides]
    width, depth = min(lengths[0], lengths[1]), max(lengths[0], lengths[1])
    front = min(street, key=lambda i: lengths[i]) if street else None
    a, b = sides[front] if front is not None else sides[lengths.index(width)]
    angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) if front is not None else None
    # Width runs along the front, depth away from it, whichever rectangle side is longer.
    width, depth = lengths[front if front is not None else lengths.index(width)], None
    depth = lengths[(front + 1) % 4] if front is not None else max(lengths)
    through = any((i + 2) % 4 in street for i in street)
    corner = any((i + 1) % 4 in street for i in street)
    return LotFrame(lot, width, depth, front, street, alley, unknown, corner, through, angle, (center.x, center.y), mid)


def envelope(frame: LotFrame, front_ft: float, side_ft: float, rear_ft: float) -> dict:
    """GeoJSON (EPSG:4326) of the lot and the area left after yards, plus the envelope's area in sq ft."""
    ox, oy = frame.origin
    local = rotate(translate(frame.lot_ft, -ox, -oy), -frame.angle_deg, origin=(0, 0))
    if frame.front_mid is None:
        return {
            "lot": mapping(transform(_TO_LL, frame.lot_ft)),
            "envelope": None,
            "envelope_area_sqft": None,
            "label": "illustrative, not survey-grade",
            "note": "street side not identified; no envelope drawn",
        }
    minx, miny, maxx, maxy = local.bounds
    fm = rotate(translate(Point(frame.front_mid), -ox, -oy), -frame.angle_deg, origin=(0, 0))
    if abs(fm.y - miny) <= abs(fm.y - maxy):
        inner = box(minx + side_ft, miny + front_ft, maxx - side_ft, maxy - rear_ft)
    else:
        inner = box(minx + side_ft, miny + rear_ft, maxx - side_ft, maxy - front_ft)
    env_local = local.intersection(inner) if inner.is_valid and not inner.is_empty else Polygon()
    env_ft = translate(rotate(env_local, frame.angle_deg, origin=(0, 0)), ox, oy)
    return {
        "lot": mapping(transform(_TO_LL, frame.lot_ft)),
        "envelope": mapping(transform(_TO_LL, env_ft)) if not env_ft.is_empty else None,
        "envelope_area_sqft": round(env_ft.area) if not env_ft.is_empty else 0,
        "front_mid": mapping(transform(_TO_LL, Point(frame.front_mid)))["coordinates"],
        "label": "illustrative, not survey-grade",
    }
