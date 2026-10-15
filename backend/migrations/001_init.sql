-- Core schema. Geometry is stored in EPSG:4326; distance and area work uses EPSG:2229 (CA State Plane V, US ft).
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

-- One row per dataset or document we ingest, with its license and dates.
CREATE TABLE source (
    id              text PRIMARY KEY,           -- stable key from sources.yaml
    name            text NOT NULL,
    publisher       text NOT NULL,
    url             text NOT NULL,
    item_id         text,
    license         text NOT NULL,
    terms_url       text,
    attribution     text,
    last_modified   timestamptz,                -- as reported by the publisher
    retrieved_at    timestamptz,                -- when we last fetched it
    mock            boolean NOT NULL DEFAULT false,
    notes           text
);

-- Parcels: allowlisted Assessor fields only. Owner, mailing address, exemptions and values are never stored.
CREATE TABLE parcel (
    apn             text PRIMARY KEY,           -- 10 digits, no dashes
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    situs_house_no  text,
    situs_fraction  text,
    situs_direction text,
    situs_street    text,
    situs_unit      text,
    situs_city      text,
    situs_zip       text,
    use_code        text,
    use_type        text,
    use_description text,
    year_built      integer,
    units           integer,
    bedrooms        integer,
    bathrooms       integer,
    sqft_main       integer,
    lot_area_sqft   double precision GENERATED ALWAYS AS (ST_Area(ST_Transform(geom, 2229))) STORED,
    source_id       text NOT NULL REFERENCES source(id),
    fetched_at      timestamptz NOT NULL
);
CREATE INDEX parcel_geom_idx ON parcel USING gist (geom);

CREATE TABLE zoning (
    id              bigserial PRIMARY KEY,
    zone_string     text NOT NULL,
    category        text,
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    source_id       text NOT NULL REFERENCES source(id),
    source_object_id bigint NOT NULL,
    fetched_at      timestamptz NOT NULL,
    UNIQUE (source_id, source_object_id)
);
CREATE INDEX zoning_geom_idx ON zoning USING gist (geom);

-- Jurisdiction and planning boundaries (city limit, community plan areas).
CREATE TABLE boundary (
    id              bigserial PRIMARY KEY,
    kind            text NOT NULL,              -- city_limit | community_plan_area
    name            text NOT NULL,
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    source_id       text NOT NULL REFERENCES source(id),
    source_object_id bigint NOT NULL,
    fetched_at      timestamptz NOT NULL,
    UNIQUE (source_id, source_object_id)
);
CREATE INDEX boundary_geom_idx ON boundary USING gist (geom);

-- Which zoning code governs a community plan area. Chapter I unless listed here.
CREATE TABLE code_regime_area (
    community_plan_area text PRIMARY KEY,
    regime          text NOT NULL CHECK (regime IN ('I', '1A')),
    effective_date  date,
    citation        text NOT NULL,              -- where we learned it
    verified        boolean NOT NULL DEFAULT false
);

CREATE TABLE overlay (
    id              bigserial PRIMARY KEY,
    kind            text NOT NULL,
    name            text,
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    source_id       text NOT NULL REFERENCES source(id),
    source_object_id bigint NOT NULL,
    fetched_at      timestamptz NOT NULL,
    UNIQUE (source_id, source_object_id)
);
CREATE INDEX overlay_geom_idx ON overlay USING gist (geom);
CREATE INDEX overlay_kind_idx ON overlay (kind);

CREATE TABLE address_point (
    id              bigserial PRIMARY KEY,
    normalized      text NOT NULL,
    house_no        text,
    street          text,
    zip             text,
    geom            geometry(Point, 4326) NOT NULL,
    source_id       text NOT NULL REFERENCES source(id),
    source_object_id bigint NOT NULL,
    fetched_at      timestamptz NOT NULL,
    UNIQUE (source_id, source_object_id)
);
CREATE INDEX address_point_norm_idx ON address_point (normalized);
CREATE INDEX address_point_geom_idx ON address_point USING gist (geom);

-- Footprints from ODbL sources live in their own table and are never merged with other data.
CREATE TABLE building_footprint_odbl (
    id              bigserial PRIMARY KEY,
    geom            geometry(Polygon, 4326) NOT NULL,
    height_m        double precision,
    source_id       text NOT NULL REFERENCES source(id),
    fetched_at      timestamptz NOT NULL
);
CREATE INDEX building_footprint_odbl_geom_idx ON building_footprint_odbl USING gist (geom);
