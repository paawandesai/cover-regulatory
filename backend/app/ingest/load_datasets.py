"""Load the datasets in sources.yaml into PostGIS.

    uv run python -m app.ingest.load_datasets            # every dataset
    uv run python -m app.ingest.load_datasets lacity_zoning lacounty_parcels
    uv run python -m app.ingest.load_datasets --area del_aire_county lacounty_parcels   # one study area only

Each run replaces that source's rows, records last_modified / retrieved_at in `source`, and prints counts.
Parcel owner and valuation fields are never requested (see the allowlist in sources.yaml).
"""

import gzip
import json
import re
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.db.connection import connect
from app.ingest.arcgis import item_last_modified, iter_features
from app.parcel.apn import InvalidAPN, normalize_apn

HERE = Path(__file__).parent
OVERLAY_NAME_FIELDS = (
    "NAME",
    "Name",
    "SPA_NM",
    "SPECIFIC_PLAN",
    "HPOZ_NAME",
    "FIRE_NAME",
    "H_TYPE",
    "NAME_ALF",
    "ZONE",
    "hqta_type",
    "CSD_NAME",
    "PASD_NAME",
    "SETBACK_NAME",
)

POLY = "ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), 3))"
POINT = "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)"


def load_config() -> tuple[list[dict], list[dict]]:
    sources = yaml.safe_load((HERE / "sources.yaml").read_text())["datasets"]
    areas = yaml.safe_load((HERE / "study_areas.yaml").read_text())["study_areas"]
    return sources, areas


def _upsert_source(conn, ds: dict, retrieved_at: datetime) -> None:
    modified = item_last_modified(ds["item_id"]) if ds.get("item_id") else None
    conn.execute(
        """INSERT INTO source (id, name, publisher, url, item_id, license, terms_url, attribution,
                               last_modified, retrieved_at, mock, notes)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false,%s)
           ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, publisher=EXCLUDED.publisher, url=EXCLUDED.url,
             item_id=EXCLUDED.item_id, license=EXCLUDED.license, terms_url=EXCLUDED.terms_url,
             attribution=EXCLUDED.attribution, last_modified=EXCLUDED.last_modified,
             retrieved_at=EXCLUDED.retrieved_at, notes=EXCLUDED.notes""",
        (
            ds["id"],
            ds["name"],
            ds["publisher"],
            ds["service_url"],
            ds.get("item_id"),
            ds["license"],
            ds.get("terms_url"),
            ds.get("attribution"),
            modified,
            retrieved_at,
            ds.get("notes"),
        ),
    )


def _int(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _norm_address(*parts) -> str:
    text = " ".join(str(p) for p in parts if p not in (None, ""))
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", text.upper())).strip()


def _features(ds: dict, areas: list[dict], fields: list[str]):
    if ds.get("scope") == "all":
        yield from iter_features(ds["service_url"], fields, where=ds.get("where", "1=1"))
        return
    for a in areas:
        yield from iter_features(ds["service_url"], fields, bbox=tuple(a["bbox"]), where=ds.get("where", "1=1"))


def load(ds: dict, areas: list[dict], only_area: bool = False) -> int:
    """With only_area, `areas` is one study area: rows of this source inside its box are replaced and the rest kept,
    so a new area can be added without re-fetching (and changing) the others."""
    now = datetime.now(UTC)
    target = ds["target"]
    n = 0
    with connect() as conn:
        _upsert_source(conn, ds, now)
        table = {
            "parcel": "parcel",
            "zoning": "zoning",
            "boundary": "boundary",
            "overlay": "overlay",
            "address_point": "address_point",
            "footprint_odbl": "building_footprint_odbl",
            "slope": "parcel_slope",
        }[target]
        if only_area and ds.get("scope") != "all":
            w, so, e, no = areas[0]["bbox"]
            conn.execute(
                f"DELETE FROM {table} WHERE source_id = %s AND ST_Intersects(geom, ST_MakeEnvelope(%s,%s,%s,%s,4326))",
                (ds["id"], w, so, e, no),
            )
        else:
            conn.execute(f"DELETE FROM {table} WHERE source_id = %s", (ds["id"],))

        if target == "slope":
            from app.ingest.slope import load_slopes

            n = load_slopes(conn, ds, now)

        elif target == "parcel":
            fmap = ds["fields"]
            for f in _features(ds, areas, list(fmap)):
                p = f["properties"]
                try:
                    apn = normalize_apn(p.get("APN") or "")
                except InvalidAPN:
                    continue
                if not f.get("geometry"):
                    continue
                vals = {col: p.get(src) for src, col in fmap.items() if col != "apn"}
                for k in ("year_built", "units", "bedrooms", "bathrooms", "sqft_main"):
                    vals[k] = _int(vals.get(k))
                cols = ["apn", *vals, "geom", "source_id", "fetched_at"]
                placeholders = ["%s"] * (1 + len(vals)) + [POLY, "%s", "%s"]
                updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols[1:])
                conn.execute(
                    f"INSERT INTO parcel ({', '.join(cols)}) VALUES ({', '.join(placeholders)}) "
                    f"ON CONFLICT (apn) DO UPDATE SET {updates}",
                    (apn, *vals.values(), json.dumps(f["geometry"]), ds["id"], now),
                )
                n += 1

        elif target == "zoning":
            src = {col: name for name, col in ds["fields"].items()}  # zone_string -> publisher's field name
            for f in _features(ds, areas, [src["zone_string"], src["category"]]):
                p = f["properties"]
                zone = (p.get(src["zone_string"]) or "").strip()
                if not f.get("geometry") or not zone:
                    continue
                conn.execute(
                    f"INSERT INTO zoning (zone_string, category, geom, source_id, source_object_id, fetched_at) "
                    f"VALUES (%s,%s,{POLY},%s,%s,%s) ON CONFLICT (source_id, source_object_id) DO NOTHING",
                    (zone, p.get(src["category"]), json.dumps(f["geometry"]), ds["id"], p["__oid"], now),
                )
                n += 1

        elif target == "boundary":
            name_field = ds.get("name_field")
            fields = [name_field] if name_field else []
            for f in _features(ds, areas, fields):
                if not f.get("geometry"):
                    continue
                name = f["properties"].get(name_field) if name_field else ds.get("name_value")
                conn.execute(
                    f"INSERT INTO boundary (kind, name, geom, source_id, source_object_id, fetched_at) "
                    f"VALUES (%s,%s,{POLY},%s,%s,%s) ON CONFLICT (source_id, source_object_id) DO NOTHING",
                    (ds["boundary_kind"], name, json.dumps(f["geometry"]), ds["id"], f["properties"]["__oid"], now),
                )
                n += 1

        elif target == "overlay":
            for f in _features(ds, areas, ["*"]):
                if not f.get("geometry"):
                    continue
                p = f["properties"]
                name = next((p[k] for k in OVERLAY_NAME_FIELDS if p.get(k)), None)
                conn.execute(
                    f"INSERT INTO overlay (kind, name, geom, source_id, source_object_id, fetched_at) "
                    f"VALUES (%s,%s,{POLY},%s,%s,%s) ON CONFLICT (source_id, source_object_id) DO NOTHING",
                    (ds["overlay_kind"], name, json.dumps(f["geometry"]), ds["id"], p["__oid"], now),
                )
                n += 1

        elif target == "address_point":
            fields = ["Number", "NumSuffix", "PreDir", "StreetName", "PostType", "PostDir", "ZipCode"]
            for f in _features(ds, areas, fields):
                p = f["properties"]
                if not f.get("geometry") or not p.get("Number"):
                    continue
                street = _norm_address(p.get("PreDir"), p.get("StreetName"), p.get("PostType"), p.get("PostDir"))
                normalized = _norm_address(p.get("Number"), p.get("NumSuffix"), street, p.get("ZipCode"))
                conn.execute(
                    f"INSERT INTO address_point (normalized, house_no, street, zip, geom, source_id, source_object_id, fetched_at) "
                    f"VALUES (%s,%s,%s,%s,{POINT},%s,%s,%s) ON CONFLICT (source_id, source_object_id) DO NOTHING",
                    (
                        normalized,
                        str(p.get("Number")),
                        street,
                        p.get("ZipCode"),
                        json.dumps(f["geometry"]),
                        ds["id"],
                        p["__oid"],
                        now,
                    ),
                )
                n += 1
        elif target == "footprint_odbl":
            # One GeoJSON feature per line; height is -1 when unknown. Keep only footprints in a study area.
            boxes = [a["bbox"] for a in areas]
            with urllib.request.urlopen(ds["service_url"], timeout=300) as resp, gzip.open(resp, "rt") as lines:
                for line in lines:
                    f = json.loads(line)
                    ring = f["geometry"]["coordinates"][0]
                    lon, lat = ring[0]
                    if not any(w <= lon <= e and s <= lat <= n_ for w, s, e, n_ in boxes):
                        continue
                    h = f["properties"].get("height")
                    conn.execute(
                        "INSERT INTO building_footprint_odbl (geom, height_m, source_id, fetched_at) "
                        "VALUES (ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, %s, %s)",
                        (json.dumps(f["geometry"]), h if h and h > 0 else None, ds["id"], now),
                    )
                    n += 1
        conn.commit()
    return n


def main(argv: list[str]) -> None:
    sources, areas = load_config()
    only = None
    if "--area" in argv:
        i = argv.index("--area")
        only, argv = argv[i + 1], argv[:i] + argv[i + 2 :]
        areas = [a for a in areas if a["id"] == only]
        if not areas:
            raise SystemExit(f"no study area {only}")
    wanted = set(argv)
    for ds in sources:
        if wanted and ds["id"] not in wanted:
            continue
        if only and ds.get("scope") == "all":
            continue  # already complete
        count = load(ds, areas, only_area=bool(only))
        print(f"{ds['id']}: {count} rows")


if __name__ == "__main__":
    main(sys.argv[1:])
