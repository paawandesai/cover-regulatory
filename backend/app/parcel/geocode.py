"""Address to point, without Google. Order: City/County address points, Assessor situs fields, then the
US Census Geocoder (public domain) as a server-side fallback. No autocomplete, no caching of results
beyond the request, and the address is never logged."""

import re

import httpx

from app.config import get_settings

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

_SUFFIXES = {
    "STREET": "ST",
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "DRIVE": "DR",
    "ROAD": "RD",
    "PLACE": "PL",
    "LANE": "LN",
    "COURT": "CT",
    "TERRACE": "TER",
    "CIRCLE": "CIR",
    "WAY": "WAY",
    "PARKWAY": "PKWY",
}
_DIRS = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}


def normalize_street_address(text: str) -> tuple[str | None, str, str | None]:
    """Split "18350 Kittridge Street, Reseda, CA 91335" into (house_no, street, zip), uppercased and abbreviated."""
    t = re.sub(r"[^A-Z0-9 ,]", " ", (text or "").upper())
    zip_m = re.search(r"\b(\d{5})(?:\s*\d{4})?\s*$", t)
    zip5 = zip_m.group(1) if zip_m else None
    first = t.split(",")[0]
    words = first.split()
    house = words[0] if words and words[0].isdigit() else None
    street_words = words[1:] if house else words
    street_words = [_DIRS.get(w, _SUFFIXES.get(w, w)) for w in street_words]
    return house, " ".join(street_words), zip5


def census_geocode(address: str) -> tuple[float, float] | None:
    """Return (lon, lat) from the US Census Geocoder, or None."""
    s = get_settings()
    try:
        r = httpx.get(
            CENSUS_URL,
            params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
            headers={"User-Agent": s.http_user_agent},
            timeout=15,
        )
        r.raise_for_status()
        matches = r.json().get("result", {}).get("addressMatches", [])
    except (httpx.HTTPError, ValueError):
        return None
    if not matches:
        return None
    c = matches[0]["coordinates"]
    return float(c["x"]), float(c["y"])
