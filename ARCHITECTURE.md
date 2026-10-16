# Architecture

The engine answers one question for a City of Los Angeles parcel: what may be built here under the R1 rules,
and what text says so. It is built around one design choice. **The AI reads the regulations once, at
ingestion, and a review step approves what it read (in this demo, an AI review applied on the owner's
instruction, recorded as `reviewed_by = 'ai-review'`). Answering a question is plain, deterministic code.** That
keeps answers repeatable, citable and fast, and it keeps the model away from addresses and user input.

```
                         INGESTION (offline, run by an operator)
 ┌──────────────────────────────┐   ┌─────────────────────────────────────────────────────────────────┐
 │ Public GIS layers            │   │ Regulation text                                                 │
 │ County parcels, City zoning, │   │ LAMC Chapter I (saved by hand), BMO/ADU ordinances, ZA Memo 143,│
 │ boundary, plan areas,        │   │ Gov. Code 66310-66342, 65852.21, Palisades rebuild FAQ          │
 │ overlays, fire perimeters,   │   └───────────────┬─────────────────────────────────────────────────┘
 │ Microsoft footprints (ODbL)  │                   │ parse, chunk by section id (12.08 C.2(a) ...)
 └──────────────┬───────────────┘                   │
                │ load_datasets.py                  ▼
                │ (owner fields dropped)   ┌───────────────────┐   fastembed nomic-embed-text-v1.5
                │                          │ reg_chunk         │◄── (local, CPU) -> pgvector
                │                          └────────┬──────────┘
                │                                   │ extract.py: Claude reads chunks into rule
                │                                   │ fragments (parameter, value, unit, verbatim quote)
                │                                   ▼
                │                          ┌───────────────────┐  validate.py (deterministic):
                │                          │ rule_fragment     │  quote must occur in the chunk,
                │                          │ pending/invalid   │  number must occur in the quote,
                │                          └────────┬──────────┘  unit must match the parameter
                │                                   │ Rule review UI (/review, password) or
                │                                   ▼ apply_review.py: approve or reject
                ▼                          ┌───────────────────┐
 ┌──────────────────────────────┐          │ rule_fragment     │
 │ PostgreSQL 16                │◄─────────│ approved          │
 │ PostGIS + pgvector           │          └───────────────────┘
 └──────────────┬───────────────┘
                │
                │            QUERY TIME (no model calls)
                ▼
 APN or address ─► resolve.py ─► stop? (outside City / Chapter 1A / not R1) ─► explicit stop result
                                   │
                                   ▼
                     geometry.py: fitted rectangle, street vs alley sides (EPSG:2229)
                                   │
                                   ▼
                     rules.py: load fragments per rule (only checked, current-text fragments)
                                   │
                                   ▼
                     assess.py: compute values, withhold where a flag makes them wrong,
                                attach citations and a label to every value
                                   │
                                   ▼
                     FastAPI /api/assess ─► Caddy ─► Vue 3 + MapLibre web app
```

## Components

| Part | Where | What it does |
|---|---|---|
| Dataset loaders | `backend/app/ingest/load_datasets.py`, `sources.yaml` | Pull public ArcGIS layers for the study areas, drop owner fields, and record source, license and fetch time. Microsoft's ODbL building footprints come from one tile filtered to the study areas, into their own table. |
| Regulation ingestion | `backend/app/ingest/regtext/` | Parse ordinance PDFs and saved HTML into chunks keyed by section id. Each chunk keeps a content hash. |
| Search | `backend/app/search/` | Exact section-id lookup first, then pgvector cosine search over local embeddings. Full-text search is the fallback. |
| Extraction | `backend/app/extract/` | Claude (model id from config, structured output) reads groups of chunks into rule fragments. Regulation text is wrapped as data. The schema has no field for status or confidence. |
| Deterministic checks | `backend/app/extract/validate.py` | Rejects a fragment whose quote is not verbatim in the chunk, whose number is not in the quote, or whose unit doesn't match. Re-running marks fragments stale when their chunk's text changes. |
| Parcel resolution | `backend/app/parcel/` | APN, then County address points, then County situs, then the Census geocoder. Then point-in-City, code regime from the Community Plan Area, and zone parsing. |
| Lot geometry | `backend/app/engine/geometry.py` | Minimum rotated rectangle in State Plane feet. Rays from each side find street (40 ft or more gap), alley (10 to 40 ft) or unknown, which sets the front. The envelope is the rectangle shrunk by the yards, labeled illustrative. |
| Rule catalogue | `backend/app/engine/rules.py` | Each rule lists the fragment inputs it needs. A rule is "derived" only if every input is approved, and "interpretive" (with a coverage share) if any input is still pending. |
| Assessment | `backend/app/engine/assess.py` | Stops early where needed, computes values, withholds flat-land values in the Hillside Area and Coastal Zone, adds flags and disclaimers. |
| API | `backend/app/api/` | FastAPI. Access logs are off and the middleware logs only the route template. Admin routes use HTTP Basic auth with scrypt. The optional invite gate is for the hosted demo. |
| Web app | `frontend/` | Vue 3 + TypeScript + MapLibre with the Forge design tokens. Assessment page, source-text panel, feedback, rule review and stop states. |
| Packaging | `docker-compose.yml`, `*/Dockerfile`, `deploy/` | Database (PostGIS + pgvector), API with the embedding model built in, Caddy serving the app, and a daily feedback purge. |

## Trust labels

| Label | Meaning |
|---|---|
| Verified parcel data | Read straight from a named dataset, with its fetch date. |
| Approximate | Machine-learned building outlines (Microsoft, ODbL), and lot width and depth fitted to the parcel outline. Shown, not survey-grade. |
| Flag, not evaluated | A condition detected from a map layer (with its dataset and fetch date) or the zone string, or a law that may apply. Not evaluated. |
| Derived from rule | Computed by code from fragments a reviewer approved, all checks passing, source text unchanged. In the hosted demo the reviewer is an AI review applied on the owner's instruction (`reviewed_by = 'ai-review'`), and the source panel says so. |
| Interpretation, confirm with City | Same computation, but at least one input fragment is still pending review (shows the share of inputs found), or a standard R1 value where something not modeled may change it (conditioned zone, specific plan or HPOZ, through lot, front taken on the long side, City ADU on a Hillside lot in a VHFHSZ). |
| Not modeled here | A flag (Hillside Area; Coastal Zone floor area and height; R1 variation zone; Height District 1-SS) makes the flat-land rule wrong, so no value is shown. |
| No cited source | An input is missing or ambiguous. No number is shown. |

The model never sets a label. Labels come from review status and the deterministic checks.

## Security and privacy controls

- The model sees only regulation text, never an address, APN or user input. Its key is read from the environment and used only by the extraction command.
- Text inside documents is treated as data. Adversarial tests show that injected instructions produce at most a pending candidate. An injected exemption whose quote lacks the number is rejected; a quote that does contain it stays a candidate until review.
- Feedback goes into a queue. It never edits rules, prompts or retrieval, and it is deleted after `FEEDBACK_RETENTION_DAYS` (1 day on the hosted demo).
- No access logs with query strings, plus `noindex` headers. Admin credentials are held in browser memory only.
- Secrets never enter the repo. A gitleaks scan runs in pre-commit and CI.

## Adding a jurisdiction

The pipeline is organised by jurisdiction, but only LA City Chapter I is built, and these parts are LA-specific:

| Part | Where | What a new jurisdiction needs |
|---|---|---|
| Boundary and code regime | `backend/app/parcel/resolve.py`, `boundary` and `code_regime_area` tables | Its boundary layer and a map from areas to the code in force there |
| Parcel and zoning layers | `backend/app/ingest/sources.yaml`, `study_areas.yaml` | Its parcel, zoning and overlay layers, with licenses |
| Zone parser | `backend/app/parcel/zone.py` | Its zone-string grammar (base zone, height district, qualifiers, suffixes) |
| Regulation text | `backend/app/ingest/regtext/` | A chunker for its code's section numbering, and sources allowed to be fetched or saved by hand |
| Rule definitions | `backend/app/engine/rules.py` | The parameters each rule needs, keyed by that code's section ids |
| Rule assembly | `backend/app/engine/assess.py` | Which rules apply to which zones, overlays that withhold or downgrade values, and the stop states |
| Golden cases | `backend/tests/golden/cases.yaml` | Parcels with expected values worked out from that code |

State ADU law (Gov. Code 66310-66342) and the geometry, labels, citations and review flow carry over unchanged to any California city.

## Scaling beyond the PoC

How this would run in production on AWS. Nothing below is built; the PoC runs as one Docker Compose host.

```
  EventBridge schedule ──► SQS "ingest" queue ──► Ingestion workers (ECS Fargate)
  (per source, per        (one message per        fetch allowed sources, chunk, hash-diff,
   jurisdiction)           document or layer)     extract changed chunks with the LLM (Bedrock or
                                                   Anthropic API, key in Secrets Manager)
                                                            │ new or changed candidates
                                                            ▼
                                                  Review queue ─► Rule review UI (licensed reviewer,
                                                            │      SSO via Cognito/OAuth, audit log)
                                                            ▼ approved fragments only
  Users ─► CloudFront + WAF ─► ALB ─► Assessment API (ECS Fargate, autoscaled, no model calls)
                                          │            │
                                          ▼            ▼
                         RDS Postgres + PostGIS   ElastiCache Redis (assessment cache,
                         + pgvector (Multi-AZ)     keyed by APN + rule-set version)
                                          ▲
  Jurisdiction plug-ins: jurisdiction → code regime → rule set → sources
  (LA City Chapter I today; Chapter 1A, LA County, other cities added as plug-ins, not forks)

  Observability: CloudWatch metrics (status codes, latency, opaque ids only), self-hosted tracing
  for extraction runs, alarms on source changes and on stale ingests.
```

What changes from the PoC:
- Ingestion becomes scheduled and incremental: a changed source re-extracts only changed chunks, and any rule
  whose chunk hash changed drops back to pending until it is re-reviewed.
- Review moves to named, licensed reviewers with SSO and an audit trail, replacing the shared admin password
  and the demo's AI review.
- The assessment API stays stateless and deterministic, so it scales horizontally; results are cached per
  APN and rule-set version.
- Every jurisdiction is a plug-in with its own code-regime map, rule set and source list.
