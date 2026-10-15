# Architecture

The engine answers one question for a City of Los Angeles parcel: what may be built here under the R1 rules,
and what text says so. It is built around one design choice. **The AI reads the regulations once, at
ingestion, and a person approves what it read. Answering a question is plain, deterministic code.** That
keeps answers repeatable, citable and fast, and it keeps the model away from addresses and user input.

```
                         INGESTION (offline, run by an operator)
 ┌──────────────────────────────┐   ┌─────────────────────────────────────────────────────────────────┐
 │ Public GIS layers            │   │ Regulation text                                                 │
 │ County parcels, City zoning, │   │ LAMC Chapter I (saved by hand), BMO/ADU ordinances, ZA Memo 143,│
 │ boundary, plan areas,        │   │ Gov. Code 66310-66342, 65852.21, Palisades rebuild FAQ          │
 │ overlays, fire perimeters    │   └───────────────┬─────────────────────────────────────────────────┘
 └──────────────┬───────────────┘                   │ parse, chunk by section id (12.08 C.2(a) ...)
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
                │                                   │ Rule review UI (/review, password)
                │                                   ▼ person approves or rejects
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
| Dataset loaders | `backend/app/ingest/load_datasets.py`, `sources.yaml` | Pull public ArcGIS layers for the study areas, drop owner fields, and record source, license and fetch time. |
| Regulation ingestion | `backend/app/ingest/regtext/` | Parse ordinance PDFs and saved HTML into chunks keyed by section id. Each chunk keeps a content hash. |
| Search | `backend/app/search/` | Exact section-id lookup first, then pgvector cosine search over local embeddings. Full-text search is the fallback. |
| Extraction | `backend/app/extract/` | Claude (model id from config, structured output) reads groups of chunks into rule fragments. Regulation text is wrapped as data. The schema has no field for status or confidence. |
| Deterministic checks | `backend/app/extract/validate.py` | Rejects a fragment whose quote is not verbatim in the chunk, whose number is not in the quote, or whose unit doesn't match. Re-running marks fragments stale when their chunk's text changes. |
| Parcel resolution | `backend/app/parcel/` | APN, then City address points, then County situs, then the Census geocoder. Then point-in-City, code regime from the Community Plan Area, and zone parsing. |
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
| Derived from rule | Computed by code from fragments a reviewer approved, all checks passing, source text unchanged. In the hosted demo the reviewer is an AI review applied on the owner's instruction (`reviewed_by = 'ai-review'`), and the source panel says so. |
| Interpretation, confirm with City | Same computation, but at least one input fragment is still pending review. Shows the share of inputs found. |
| No cited source | An input is missing, ambiguous or withheld. No number is shown. |

The model never sets a label. Labels come from review status and the deterministic checks.

## Security and privacy controls

- The model sees only regulation text, never an address, APN or user input. Its key is read from the environment and used only by the extraction command.
- Text inside documents is treated as data. Adversarial tests show that injected instructions produce at most a pending candidate, and no input can produce a zero setback.
- Feedback goes into a queue. It never edits rules, prompts or retrieval, and the hosted demo deletes it after 14 days.
- No access logs with query strings, plus `noindex` headers. Admin credentials are held in browser memory only.
- Secrets never enter the repo. A gitleaks scan runs in pre-commit and CI.

## Scaling beyond the PoC

The production shape would be:
- Scheduled ingestion workers on a queue.
- An API on ECS.
- RDS Postgres with PostGIS and pgvector.
- Secrets in Secrets Manager.
- Jurisdiction plug-ins (`jurisdiction → code regime → rule set → sources`), so adding LA County or another city means adding a plug-in, not forking the engine.
