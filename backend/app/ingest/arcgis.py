"""Minimal, polite client for public ArcGIS REST feature/map services.

Fetches one layer at a time as GeoJSON, filtered by bounding box, paginated with resultOffset, with a
delay between pages. Only the fields we ask for are requested, so unwanted attributes (e.g. owner or
valuation data) never leave the server.
"""

import time
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx

from app.config import get_settings


class ArcGISError(RuntimeError):
    pass


def _client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(timeout=90, headers={"User-Agent": s.http_user_agent}, follow_redirects=True)


def layer_info(layer_url: str) -> dict:
    with _client() as c:
        info = c.get(layer_url, params={"f": "json"}).json()
    if "error" in info:
        raise ArcGISError(f"{layer_url}: {info['error']}")
    return info


def item_last_modified(item_id: str) -> datetime | None:
    with _client() as c:
        meta = c.get(f"https://www.arcgis.com/sharing/rest/content/items/{item_id}", params={"f": "json"}).json()
    ms = meta.get("modified")
    return datetime.fromtimestamp(ms / 1000, UTC) if ms else None


def iter_features(
    layer_url: str,
    out_fields: list[str],
    bbox: tuple[float, float, float, float] | None = None,
    where: str = "1=1",
) -> Iterator[dict]:
    """Yield GeoJSON features (EPSG:4326) from a layer, optionally limited to a WGS84 bbox."""
    info = layer_info(layer_url)
    page = int(info.get("maxRecordCount") or 1000)
    paginates = bool(info.get("advancedQueryCapabilities", {}).get("supportsPagination", False))
    oid_field = info.get("objectIdField") or "OBJECTID"
    fields = ["*"] if "*" in out_fields else sorted(set(out_fields) | {oid_field})
    params: dict = {
        "where": where,
        "outFields": ",".join(fields),
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "geojson",
        "orderByFields": oid_field,
    }
    if bbox:
        params |= {
            "geometry": ",".join(map(str, bbox)),
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
        }
    delay = get_settings().arcgis_page_delay_s
    offset = 0
    with _client() as c:
        while True:
            q = dict(params)
            if paginates:
                q |= {"resultOffset": offset, "resultRecordCount": page}
            r = c.get(f"{layer_url}/query", params=q)
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                raise ArcGISError(f"{layer_url}: {body['error']}")
            feats = body.get("features", [])
            for f in feats:
                f.setdefault("properties", {})["__oid"] = f["properties"].get(oid_field, f.get("id"))
                yield f
            more = body.get("exceededTransferLimit") or body.get("properties", {}).get("exceededTransferLimit")
            if not paginates or not feats or not more:
                return
            offset += len(feats)
            time.sleep(delay)
