"""Resolve an APN or address to a parcel and everything the rule engine needs to know about where it is.

The order matters and is fixed:
  1. find the parcel
  2. point-in-City test (outside the City -> stop, explicit result)
  3. code regime from the Community Plan Area (Chapter 1A -> stop, explicit result)
  4. zone string, overlays, lot facts
"""

from dataclasses import dataclass, field

from app.db.connection import connect
from app.parcel.apn import InvalidAPN, looks_like_apn, normalize_apn
from app.parcel.geocode import census_geocode, normalize_street_address
from app.parcel.provenance import Sourced
from app.parcel.zone import ParsedZone, parse_zone


class ParcelNotFound(LookupError):
    pass


@dataclass
class ParcelContext:
    apn: str
    status: str  # ok | outside_city | regime_not_modeled
    matched_by: str  # apn | address_point | situs | census
    in_city: bool
    jurisdiction_hint: str | None
    community_plan_area: Sourced | None
    code_regime: Sourced | None
    zone_strings: list[Sourced] = field(default_factory=list)
    zone: ParsedZone | None = None
    split_zoned: bool = False
    overlays: list[dict] = field(default_factory=list)
    lot_area_sqft: Sourced | None = None
    use: Sourced | None = None
    existing: Sourced | None = None
    situs: Sourced | None = None
    parcel_source: Sourced | None = None
    notes: list[str] = field(default_factory=list)


def _find_apn(conn, query: str) -> tuple[str, str]:
    if looks_like_apn(query):
        apn = normalize_apn(query)
        if conn.execute("SELECT 1 FROM parcel WHERE apn=%s", (apn,)).fetchone():
            return apn, "apn"
        raise ParcelNotFound("No parcel with that APN in the loaded data.")

    house, street, zip5 = normalize_street_address(query)
    if house and street:
        pattern = f"{house} {street}%"
        row = conn.execute(
            """SELECT p.apn FROM address_point a JOIN parcel p ON ST_Intersects(p.geom, a.geom)
               WHERE a.normalized LIKE %s AND (%s::text IS NULL OR a.zip = %s) LIMIT 1""",
            (pattern, zip5, zip5),
        ).fetchone()
        if row:
            return row["apn"], "address_point"
        row = conn.execute(
            """SELECT apn FROM parcel WHERE situs_house_no=%s AND upper(situs_street) LIKE %s
               AND (%s::text IS NULL OR left(situs_zip,5)=%s) LIMIT 1""",
            (house, f"{street}%", zip5, zip5),
        ).fetchone()
        if row:
            return row["apn"], "situs"

    pt = census_geocode(query)
    if pt:
        row = conn.execute(
            "SELECT apn FROM parcel WHERE ST_Intersects(geom, ST_SetSRID(ST_Point(%s,%s),4326)) LIMIT 1", pt
        ).fetchone()
        if row:
            return row["apn"], "census"
    raise ParcelNotFound("Address not found in the loaded data. Try the APN instead.")


def _city_name(situs_city: str | None) -> str:
    if not situs_city:
        return "outside the City of Los Angeles (no situs city on the Assessor record)"
    name = situs_city.upper().removesuffix(" CA").removesuffix(" CALIF").strip()
    return name.title()


def resolve(query: str) -> ParcelContext:
    with connect() as conn:
        try:
            apn, matched_by = _find_apn(conn, query)
        except InvalidAPN as e:
            raise ParcelNotFound(str(e)) from e

        p = conn.execute(
            """SELECT p.*, s.id AS sid, ST_AsText(ST_PointOnSurface(p.geom)) AS pos
               FROM parcel p JOIN source s ON s.id = p.source_id WHERE apn=%s""",
            (apn,),
        ).fetchone()
        sid, fetched = p["sid"], p["fetched_at"]
        ctx_common = {
            "apn": apn,
            "matched_by": matched_by,
            "lot_area_sqft": Sourced(round(p["lot_area_sqft"]), sid, fetched),
            "use": Sourced(
                {"code": p["use_code"], "type": p["use_type"], "description": p["use_description"]}, sid, fetched
            ),
            "existing": Sourced(
                {k: p[k] for k in ("year_built", "units", "bedrooms", "bathrooms", "sqft_main")}, sid, fetched
            ),
            "situs": Sourced(
                {k: p[k] for k in ("situs_house_no", "situs_direction", "situs_street", "situs_city", "situs_zip")},
                sid,
                fetched,
            ),
            "parcel_source": Sourced(sid, sid, fetched),
        }

        city = conn.execute(
            """SELECT b.source_id, b.fetched_at FROM boundary b, parcel p
               WHERE p.apn=%s AND b.kind='city_limit' AND ST_Intersects(b.geom, ST_PointOnSurface(p.geom))""",
            (apn,),
        ).fetchone()
        if not city:
            return ParcelContext(
                status="outside_city",
                in_city=False,
                jurisdiction_hint=_city_name(p["situs_city"]),
                community_plan_area=None,
                code_regime=None,
                notes=["Parcel is outside the City of Los Angeles; City zoning does not apply."],
                **ctx_common,
            )

        cpa = conn.execute(
            """SELECT b.name, b.source_id, b.fetched_at, r.regime, r.citation, r.verified
               FROM boundary b JOIN parcel p ON ST_Intersects(b.geom, ST_PointOnSurface(p.geom))
               LEFT JOIN code_regime_area r ON r.community_plan_area = b.name
               WHERE p.apn=%s AND b.kind='community_plan_area' LIMIT 1""",
            (apn,),
        ).fetchone()
        cpa_val = Sourced(cpa["name"], cpa["source_id"], cpa["fetched_at"]) if cpa else None
        regime = cpa["regime"] if cpa and cpa["regime"] else "I"
        regime_val = Sourced(
            regime,
            "code_regime_area" if cpa and cpa["regime"] else None,
            None,
            "verified" if (not cpa or not cpa["regime"] or cpa["verified"]) else "interpretive",
        )

        zones = conn.execute(
            """SELECT z.zone_string, z.source_id, z.fetched_at,
                      ST_Area(ST_Transform(ST_Intersection(z.geom, p.geom), 2229)) / NULLIF(ST_Area(ST_Transform(p.geom, 2229)),0) AS share,
                      ST_Intersects(z.geom, ST_PointOnSurface(p.geom)) AS at_center
               FROM zoning z JOIN parcel p ON ST_Intersects(z.geom, p.geom)
               WHERE p.apn=%s ORDER BY share DESC""",
            (apn,),
        ).fetchall()
        # Ignore slivers from digitizing differences between the parcel and zoning layers.
        zones = [z for z in zones if (z["share"] or 0) >= 0.02]
        zone_vals = [Sourced(z["zone_string"], z["source_id"], z["fetched_at"]) for z in zones]
        primary = next((z for z in zones if z["at_center"]), zones[0] if zones else None)
        parsed = parse_zone(primary["zone_string"]) if primary else None
        if parsed and parsed.regime_hint == "1A":
            regime = "1A"
            regime_val = Sourced("1A", primary["source_id"], primary["fetched_at"])

        overlays = conn.execute(
            """SELECT o.kind, o.name, o.source_id, o.fetched_at FROM overlay o JOIN parcel p ON ST_Intersects(o.geom, p.geom)
               WHERE p.apn=%s ORDER BY o.kind""",
            (apn,),
        ).fetchall()

        notes = []
        if len({z["zone_string"] for z in zones}) > 1:
            notes.append(
                "Parcel is split-zoned; the zone at the parcel's interior point is used, and the others are listed."
            )
        if not zones:
            notes.append("No zoning polygon found for this parcel in the loaded data.")

        return ParcelContext(
            status="regime_not_modeled" if regime == "1A" else "ok",
            in_city=True,
            jurisdiction_hint="City of Los Angeles",
            community_plan_area=cpa_val,
            code_regime=regime_val,
            zone_strings=zone_vals,
            zone=parsed,
            split_zoned=len({z["zone_string"] for z in zones}) > 1,
            overlays=[dict(o) for o in overlays],
            notes=notes,
            **ctx_common,
        )
