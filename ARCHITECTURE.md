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
 │ boundary, plan areas,        │   │ Gov. Code 66310-66342, SB 9, Mayor's EOs 1/8/9, rebuild FAQ     │
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
| Slope bands | `backend/app/ingest/slope.py` | For each Hillside Area parcel, samples the USGS 3DEP elevation model on a grid of about 3 ft, computes slope per cell and stores the area in each LAMC 12.21 C.10(b) slope band (`parcel_slope`). An estimate of the surveyed slope analysis map. |
| Table reader | `backend/app/extract/tables.py` | Reads the R1 variation and Hillside tables cell by cell (no model) into pending candidates, checked like model output. |
| Regulation ingestion | `backend/app/ingest/regtext/` | Parse ordinance PDFs and saved HTML into chunks keyed by section id. Each chunk keeps a content hash. |
| Source check | `backend/app/ingest/regtext/refresh.py`, `source_check` table | Weekly (compose `refresh` service): re-downloads each `fetch: url` document and compares SHA-256. A changed file is re-ingested; each decided rule on a changed chunk goes back to pending if its quote is still verbatim, or is retired if not, with an audit entry. Hand-saved sources are never fetched and are listed as due after 90 days. Results show on the Sources tab of Rule review. |
| Search | `backend/app/search/` | Exact section-id lookup first, then pgvector cosine search over local embeddings. Full-text search is the fallback. |
| Extraction | `backend/app/extract/` | Claude (model id from config, structured output) reads groups of chunks into rule fragments. Regulation text is wrapped as data. The schema has no field for status or confidence. |
| Deterministic checks | `backend/app/extract/validate.py` | Rejects a fragment whose quote is not verbatim in the chunk, whose number is not in the quote, or whose unit doesn't match. Re-running marks fragments stale when their chunk's text changes. |
| Parcel resolution | `backend/app/parcel/` | APN, then County address points, then County situs, then the Census geocoder. Then point-in-City, code regime from the Community Plan Area, and zone parsing. |
| Lot geometry | `backend/app/engine/geometry.py` | Minimum rotated rectangle in State Plane feet. Rays from each side find street (40 ft or more gap), alley (10 to 40 ft) or unknown, which sets the front. The envelope is the rectangle shrunk by the yards, labeled illustrative. |
| Rule catalogue | `backend/app/engine/rules.py` | Each rule lists the fragment inputs it needs. A rule is "derived" only if every input is approved, and "interpretive" (with a coverage share) if any input is still pending. |
| Assessment | `backend/app/engine/assess.py`, `zones.py` | Stops early where needed, computes values (R1 in `assess.py`, R2 and RE in `zones.py`, specific plans that have been read in `plans.py`, the Chapter 1A zone string and density in `ch1a.py`), applies the Hillside Area (with slope bands from `app/ingest/slope.py`), Coastal Zone and R1 variation tables, withholds what is not modeled, adds flags and disclaimers. |
| SB 9 and fire orders | `backend/app/engine/orders.py` | SB 9 two-unit and lot-split tests, Executive Order 9's suspension, and the EO 1 like-for-like and EO 8 Coastal Zone rebuild limits. |
| Client reports | `backend/app/api/reports.py`, `report` table | Freezes an assessment into a report keyed by an unguessable token. The public link returns only the status until an admin signs with name and license; withdrawn reports return 404. |
| Follow-up chat | `backend/app/api/chat.py` | Builds the prompt from the assessment's values (10-digit numbers scrubbed) and retrieved chunks as delimited data; the model returns sentences with quotes or item ids (structured output, no tools). Each quote is checked verbatim against its chunk; failing sentences are dropped. |
| API | `backend/app/api/` | FastAPI. Access logs are off and the middleware logs only the route template. Admin routes use HTTP Basic auth with scrypt, against named reviewer accounts (`reviewer` table, managed with `python -m app.api.reviewers`) or the bootstrap `ADMIN_USERNAME`. Every review action writes an `audit_log` row in the same transaction; a trigger makes the log append-only, and report entries hold a hash of the link token, never the link. The optional invite gate is for the hosted demo. |
| Web app | `frontend/` | Vue 3 + TypeScript + MapLibre with the Forge design tokens. Assessment page, source-text panel, feedback, rule review and stop states. |
| Packaging | `docker-compose.yml`, `*/Dockerfile`, `deploy/` | Database (PostGIS + pgvector), API with the embedding model built in, Caddy serving the app, and a daily feedback purge. |

## Trust labels

| Label | Meaning |
|---|---|
| Verified parcel data | Read straight from a named dataset, with its fetch date. |
| Approximate | Machine-learned building outlines (Microsoft, ODbL), and lot width and depth fitted to the parcel outline. Shown, not survey-grade. |
| Flag, not evaluated | A condition detected from a map layer (with its dataset and fetch date) or the zone string, or a law that may apply. Not evaluated. |
| Derived from rule | Computed by code from fragments a reviewer approved, all checks passing, source text unchanged. In the hosted demo the reviewer is an AI review applied on the owner's instruction (`reviewed_by = 'ai-review'`), and the source panel says so. |
| Interpretation, confirm with City | Same computation, but at least one input fragment is still pending review (shows the share of inputs found), or a standard R1 value where something not modeled may change it (conditioned zone, a specific plan or HPOZ whose text is not loaded, through lot, front taken on the long side, City ADU on a Hillside lot in a VHFHSZ). |
| Not modeled here | A flag makes the standard rule wrong and the replacement is not modeled (Coastal Zone outside Height District 1), so no value is shown. |
| No cited source | An input is missing or ambiguous. No number is shown. |

The model never sets a label. Labels come from review status and the deterministic checks.

## Security and privacy controls

- At extraction the model sees only regulation text. The follow-up chat also sends the user's question and the assessment's values, never an address or APN (10-digit numbers are scrubbed from both). The key is read from the environment; without it the chat returns 503 and nothing else changes.
- Chat answers are checked, not trusted: a sentence survives only if every quote is verbatim in the chunk it names or it points at a real assessment value. The question is not logged or stored, and it is rate limited (30 an hour per client).
- Client report links show nothing but the status until a reviewer signs; reports store the APN, never a typed address, and are purged with feedback.
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

How this would run in production on AWS. The PoC runs as one Docker Compose host. The serving part (CloudFront and WAF, ALB, the API on ECS Fargate with autoscaling, RDS Multi-AZ with backups, scheduled jobs, alarms) is written as Terraform in `infra/aws/` and checked in CI, but not applied; `infra/aws/README.md` has the runbook and a cost estimate. The ingestion queue, SSO and the Redis cache below are not written yet.

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
- Ingestion is scheduled (built for downloadable sources: a weekly check re-ingests a changed file and sends
  every rule whose chunk changed back to review). Next: re-extract only the changed chunks automatically, and
  alert by email or chat rather than only on the Sources tab.
- Review moves from local named accounts (built) to SSO through the organisation's identity provider, keeping the
  same audit log, and licensed reviewers replace the demo's AI review.
- The assessment API stays stateless and deterministic, so it scales horizontally; results are cached per
  APN and rule-set version.
- Every jurisdiction is a plug-in with its own code-regime map, rule set and source list.
