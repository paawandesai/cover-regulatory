// Shapes returned by the FastAPI backend (backend/app/api/main.py, backend/app/engine/assess.py).

export type Label = 'verified' | 'derived' | 'interpretive' | 'uncited'

export interface Citation {
  fragment_id: number | null
  chunk_id: string | null
  section_id: string
  quote: string | null
  quote_start: number | null
  quote_end: number | null
  review_status: 'pending' | 'approved' | 'code-cited' | string
  source_url: string | null
  retrieved_at: string | null
}

export interface Item {
  id: string
  family: string
  title: string
  value: unknown
  unit: string | null
  label: Label
  rule_id: string | null
  coverage: number | null
  explanation: string | null
  citations: Citation[]
  source: { dataset: string | null; fetched_at: string | null } | null
  label_text: string
}

export type Status = 'ok' | 'outside_city' | 'regime_not_modeled' | 'zone_not_modeled'

export interface Geometry {
  lot: GeoJSON.Polygon | GeoJSON.MultiPolygon
  envelope: GeoJSON.Polygon | GeoJSON.MultiPolygon | null
  envelope_area_sqft: number | null
  front_mid?: [number, number]
  label: string
  note?: string
  yards_ft: { front: number; side: number; rear: number } | null
}

export interface Assessment {
  generated_at: string
  status: Status
  parcel: { apn: string; matched_by: string; jurisdiction: string | null; items: Item[] }
  notes: string[]
  items: Item[]
  geometry: Geometry | null
  disclaimers: string[]
  ai_disclosure: string
}

export interface Chunk {
  id: string
  section_id: string
  heading: string | null
  text: string
  source_url: string | null
  retrieved_at: string | null
  document_title: string
  publisher: string | null
  manual_retrieval: boolean
  mock: boolean
}

export interface Fragment {
  id: number
  rule_family: string
  parameter: string
  applies_to: string | null
  conditions: string | null
  value_numeric: number | null
  unit: string | null
  value_text: string | null
  source_quote: string
  quote_start: number | null
  quote_end: number | null
  validation: string
  status: 'pending' | 'approved' | 'rejected' | 'invalid'
  reviewed_by: string | null
  reviewed_at: string | null
  review_note: string | null
  chunk_id: string
  section_id: string
  chunk_text: string
  source_url: string | null
  served_model: string | null
  prompt_version: string | null
}
