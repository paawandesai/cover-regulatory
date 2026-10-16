-- Slope bands per Hillside Area parcel, computed at ingestion from the USGS 3DEP elevation model (public domain).
-- Used for the Hillside Area floor area (LAMC 12.21 C.10(b)); an estimate, not the surveyed slope analysis map
-- the code requires with a permit.
CREATE TABLE IF NOT EXISTS parcel_slope (
    apn text PRIMARY KEY REFERENCES parcel (apn) ON DELETE CASCADE,
    band_sqft jsonb NOT NULL,          -- {"0-14.99": sq ft, "15-29.99": ..., "100+": ...}
    resolution_ft double precision NOT NULL,
    cells integer NOT NULL,
    source_id text NOT NULL REFERENCES source (id),
    fetched_at timestamptz NOT NULL
);
