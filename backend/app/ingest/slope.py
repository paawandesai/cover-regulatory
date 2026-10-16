"""Slope bands for Hillside Area parcels, from the USGS 3DEP elevation model (public domain).

LAMC 12.21 C.10(b) sets the Hillside floor area from the lot area in each slope band (0-14.99%, 15-29.99%, ...),
which the code takes from a surveyed slope analysis map. This is an estimate of that map: elevation is sampled on a
grid of about 3 ft over each parcel, slope is the steepest gradient at each cell, and each cell inside the parcel
counts towards its band. The engine labels anything built on it as an interpretation to confirm on a survey.
"""

import io
import json
import logging
import math
import time
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image
from shapely import contains_xy, wkb

from app.engine.geometry import _TO_FT, transform

log = logging.getLogger(__name__)

BANDS = [(0, 15, "0-14.99"), (15, 30, "15-29.99"), (30, 45, "30-44.99"), (45, 60, "45-59.99"), (60, 100, "60-99.99")]
STEEP = "100+"
CELL_FT = 3.28084  # 1 m, the 3DEP 1/9 arc-second resolution where available
M_TO_FT = 3.28084
MAX_CELLS = 400


def band_areas(slope_pct: np.ndarray, inside: np.ndarray, cell_ft: float) -> dict[str, float]:
    """Square feet of the lot in each slope band (cells inside the lot only)."""
    cell = cell_ft * cell_ft
    s = slope_pct[inside]
    out = {label: float(((s >= lo) & (s < hi)).sum() * cell) for lo, hi, label in BANDS}
    out[STEEP] = float((s >= 100).sum() * cell)
    return out


def slope_percent(elev_ft: np.ndarray, cell_ft: float) -> np.ndarray:
    gy, gx = np.gradient(elev_ft, cell_ft)
    return np.hypot(gx, gy) * 100


def _fetch(service_url: str, bbox: tuple[float, float, float, float], nx: int, ny: int) -> np.ndarray:
    for attempt in range(4):
        try:
            return _fetch_once(service_url, bbox, nx, ny)
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2**attempt)
    raise AssertionError


def _fetch_once(service_url: str, bbox: tuple[float, float, float, float], nx: int, ny: int) -> np.ndarray:
    q = urllib.parse.urlencode(
        {
            "bbox": ",".join(f"{v:.2f}" for v in bbox),
            "bboxSR": 2229,
            "imageSR": 2229,
            "size": f"{nx},{ny}",
            "format": "tiff",
            "pixelType": "F32",
            "interpolation": "RSP_BilinearInterpolation",
            "f": "image",
        }
    )
    with urllib.request.urlopen(f"{service_url}/exportImage?{q}", timeout=60) as r:
        return np.array(Image.open(io.BytesIO(r.read())), dtype=float) * M_TO_FT


def load_slopes(conn, ds: dict, now, missing_only: bool = False) -> int:
    rows = conn.execute(
        """SELECT DISTINCT p.apn, ST_AsBinary(p.geom) AS g FROM parcel p
           JOIN overlay o ON o.kind = 'hillside' AND ST_Intersects(o.geom, p.geom)
           JOIN zoning z ON ST_Intersects(z.geom, ST_PointOnSurface(p.geom))
           WHERE z.zone_string ~ 'R1'  -- only R1-family lots are assessed
             AND (NOT %s OR p.apn NOT IN (SELECT apn FROM parcel_slope))""",
        (missing_only,),
    ).fetchall()
    n = 0
    for r in rows:
        lot = transform(_TO_FT, wkb.loads(bytes(r["g"])))
        minx, miny, maxx, maxy = lot.bounds
        pad = 2 * CELL_FT
        minx, miny, maxx, maxy = minx - pad, miny - pad, maxx + pad, maxy + pad
        cell = max(CELL_FT, max(maxx - minx, maxy - miny) / MAX_CELLS)
        nx, ny = math.ceil((maxx - minx) / cell), math.ceil((maxy - miny) / cell)
        try:
            elev = _fetch(ds["service_url"], (minx, miny, minx + nx * cell, miny + ny * cell), nx, ny)
        except OSError as e:
            log.warning("elevation fetch failed for one parcel: %s", type(e).__name__)
            continue
        # Row 0 of the image is the top (north) edge.
        xs = minx + (np.arange(nx) + 0.5) * cell
        ys = miny + ny * cell - (np.arange(ny) + 0.5) * cell
        gx, gy = np.meshgrid(xs, ys)
        inside = contains_xy(lot, gx, gy)
        if not inside.any():
            continue
        bands = band_areas(slope_percent(elev, cell), inside, cell)
        conn.execute(
            """INSERT INTO parcel_slope (apn, band_sqft, resolution_ft, cells, source_id, fetched_at)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (apn) DO UPDATE SET band_sqft = EXCLUDED.band_sqft, resolution_ft = EXCLUDED.resolution_ft,
                   cells = EXCLUDED.cells, source_id = EXCLUDED.source_id, fetched_at = EXCLUDED.fetched_at""",
            (r["apn"], json.dumps(bands), cell, int(inside.sum()), ds["id"], now),
        )
        n += 1
        if n % 50 == 0:
            conn.commit()
            log.info("slope bands: %d parcels", n)
    return n


if __name__ == "__main__":
    # Fill in parcels a previous run could not fetch: python -m app.ingest.slope
    from datetime import UTC, datetime
    from pathlib import Path

    import yaml

    from app.db.connection import connect

    logging.basicConfig(level=logging.INFO)
    sources = yaml.safe_load((Path(__file__).with_name("sources.yaml")).read_text())["datasets"]
    ds = next(d for d in sources if d["id"] == "usgs_3dep")
    with connect() as conn:
        print(load_slopes(conn, ds, datetime.now(UTC), missing_only=True))
        conn.commit()
