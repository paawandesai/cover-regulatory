# Home Building Regulatory Engine (proof of concept)

Decision support for licensed architects and engineers. Given a City of Los Angeles parcel (APN or address), the engine reports which zoning constraints apply to a single-family home, an ADU/JADU, or a guest house, and why. Every claim is tied to the regulatory text it came from and labeled by how it was established.

**This is not a zoning determination.** Outputs must be reviewed by a licensed professional and confirmed with the jurisdiction before they are relied on or shared with a client. Parcel geometry from the County carries its disclaimer: not for legal, engineering, or surveying use.

> Status: proof of concept, built 2026-10-15. The database holds four small, self-selected study areas (Reseda, Boyle Heights, Pacific Palisades and a Westside strip on the Beverly Hills edge; `backend/app/ingest/study_areas.yaml`), so parcels outside them return "not found". Hosted demo (invite only): https://34-213-114-35.sslip.io. Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## What it does
Enter an APN or a street address. The engine:

1. **Finds the parcel and stops early when it must.** Outside the City, under Chapter 1A, or not an R1-family zone each gets an explicit result instead of wrong rules.
2. **Reports the R1 envelope:** front, side and rear yards, maximum residential floor area, height, and whether the lot meets the R1 minimums.
3. **Reports what can be built besides the house:** a detached ADU under state law (800 sq ft) and under the City ordinance (up to 1,200 sq ft), an attached ADU, a JADU (500 sq ft), and a guest house (allowed only on lots of 10,000 sq ft or more).
4. **Flags what it does not apply:** Hillside Area, Coastal Zone, Very High Fire Hazard Severity Zone, the January 2025 fire rebuild orders, overlay plans, zone conditions and SB 9. Where a flag means the flat-land rule is wrong (Hillside, Coastal Zone floor area), the value is withheld, not shown.
5. **Labels every value** with how it was established:
   - **Verified parcel data:** read from a named dataset with its fetch date.
   - **Derived from rule:** computed from regulation text that a review approved (in this demo, an AI review; see Known constraints). Flags and lot dimensions computed from geometry are also Derived.
   - **Interpretation, confirm with City:** computed from text that an AI read but no review has approved yet (it shows how many of the rule's inputs were found), or a standard R1 value on an R1 variation or conditioned zone the engine does not model.
   - **Not modeled here:** a flag makes the flat-land rule wrong (Hillside Area, Coastal Zone floor area). No number is shown.
   - **Approximate (imagery):** machine-learned building outlines. Shown for context, never used in a rule.
   - **No cited source:** an input is missing or the rule doesn't apply. No number is shown.
6. **Shows the source.** Clicking any value opens the regulation text with the supporting quote highlighted, plus a link to the official source.
7. **Draws the lot.** A diagram or map shows the lot and the buildable area left after yards. It is labeled illustrative, not survey-grade.
8. **Takes feedback without letting it change anything.** "Report a problem" queues a note for a reviewer. Feedback never changes a rule. A rule changes status only through a review decision: the password-protected Rule review screen (`/review`), or the `apply_review` command that applied this demo's AI review.

No AI model runs when you ask for an assessment. The AI work happens once, at ingestion: a model reads the regulation text into candidate rule fragments, each with a verbatim quote. A deterministic check rejects any fragment whose quote is not in the text or whose number is not in the quote. Answers are therefore repeatable and fast.

## What it does NOT do
- It does not cover jurisdictions outside the City of Los Angeles. Such parcels get an explicit "outside City of Los Angeles" result.
- It does not model LAMC Chapter 1A (the new Zoning Code, in effect in the Downtown and Boyle Heights Community Plan Areas). Those parcels get a "code regime not modeled" result.
- It models only the R1 zone family. Hillside Area, R1 Variation Zones, HPOZs, specific plans, the Coastal Zone, fire hazard zones, SB 9, and the January 2025 fire rebuild orders are detected and flagged, not applied.
- Setback and buildable-area geometry is illustrative, not survey-grade.
- It does not consider private covenants (CC&Rs), demographic data, or owner information.
- Existing buildings are shown as approximate Microsoft machine-learned outlines (ODbL). They can miss, merge or misplace buildings. The Assessor's building attributes are shown when recorded.
- It has no project-inputs form (bedrooms, proposed floor area, height). The assessment depends on the parcel only.
- The map has no interactive annotations beyond pan and zoom; values are explained in the side panel instead.
- There is no chat. The plan's read-only follow-up chat was not built.
- There is no client-facing report or export, so there is no architect sign-off gate yet. Any report built later must sit behind a licensed reviewer's sign-off and disclose AI involvement.
- The fire rebuild flag cites City Planning's Palisades Rebuild FAQ (2026-01-30), which summarizes Emergency Executive Orders 1 and 8. The orders' own text was not ingested, so check the current order before relying on the flag.
- An address that matches no County address point or parcel situs is sent to the US Census Geocoder (a public, no-account service). APN searches never leave the server.
- Sign-in and invite-code attempts are not rate-limited.
- Prevailing front-yard setbacks, garage floor-area exemptions, transit-proximity ADU height increases and multi-story side-yard increments are named in the explanations but not computed.

## Known constraints
Places where a project guardrail overrides a requirement in the brief. The brief is paraphrased, not quoted.

| The brief asks for | What this tool does instead, and why |
|---|---|
| Cutting regulatory research effort to zero | It cuts the time to a **validated** answer. It is decision support: a licensed professional reviews the cited output and confirms with the City. "Zero" is neither safe nor measurable. |
| Possibly GCP for geocoding | No Google services. The APN path needs no geocoder. Addresses resolve through County address points, then County parcel situs, then the US Census Geocoder (public domain). |
| The latest AI technology | A generally available model, pinned by id in configuration (`LLM_MODEL_ID`), used only at ingestion. |
| Testing on parcels Cover would provide | None were delivered. The golden cases are **self-selected** parcels (vacant or City-owned where possible), identified by APN only. |
| More specific resources from Cover | None were invented. Sources are official City, County and State publications. The LAMC text was saved by hand from the City's code publisher, not crawled. |
| Rules approved by a person before use | In this demo the 230 rule candidates were reviewed by AI, at the project owner's instruction: a three-way check (source text, a second model, official sources) decided each one, and 8 were rejected. Values labelled "Derived from rule" therefore rest on an AI review, which the source panel says. A person should re-review before relying on them (see `AI_USAGE.md`). |
| Feedback that improves future answers | Feedback is queued for a reviewer and never edits rules, prompts or retrieval automatically. |
| Scaling to LA County, California and beyond | Only LA City, Chapter I, R1 is implemented. The design is jurisdiction-pluggable (jurisdiction → code regime → rule set → sources), but nothing else is modeled. |
| Developing on synthetic data only, with a "Demo — synthetic data only" banner (guardrail) | The brief asks for public parcel and zoning data, so the engine uses real public County and City layers with owner fields dropped at ingestion. Fixtures are APNs only, with no addresses. Because "synthetic" would be untrue, the hosted banner reads "Hosted demo with public data only. Please don't enter personal information." |
| Visualizing existing buildings | Uses Microsoft's machine-learned footprints (ODbL), kept in their own table and labelled approximate. The County building outlines were not used because their license is unclear. Footprints can miss, merge or misplace buildings. |

## Data sources and licenses
See `LICENSES.md` for code dependencies and `backend/app/ingest/sources.yaml` for every dataset and document, with its license and item id. Retrieval dates are recorded in the `source` table at load time and shown beside each value.

## Measured results
Measured 2026-10-15 on the development machine (4 CPU cores, no GPU, Postgres on the same machine).

**Golden parcels** (`backend/tests/golden/`): 8 of 8 pass. The expected values were calculated by Claude Code (the coding assistant) from the code text and the parcel data, not copied from the engine's output, then compared with the engine. No person has checked them yet (decision D17). Every value the engine shows on these parcels is asserted (66 values, plus the status and flags of each case).

| APN | Case | Front / side / rear (ft) | Max floor area (sq ft) | Height (ft) | Guest house | Flags |
|---|---|---|---|---|---|---|
| 2121-005-008 | Reseda R1-1, 60 x 135 ft | 20 / 5 / 15 | 3,645 | 33 | Not allowed | SB 9 |
| 2121-016-012 | Reseda R1-1, exactly 50 ft wide | 20 / 5 / 15 | 2,453 | 33 | Not allowed | SB 9 |
| 2121-002-004 | Reseda R1-1, 25 ft wide (substandard) | 20 / 3 / 15 | 1,462 | 33 | Not allowed | SB 9 |
| 4359-016-023 | R1-1, 16,403 sq ft, inside a specific plan | 20 / 5 / 15 | 7,381 | 33 | Allowed | Overlay plan, SB 9 |
| 4412-014-028 | Pacific Palisades, Hillside + Coastal + fire | Withheld | Withheld | Withheld | Allowed | Fire rebuild, Hillside, Coastal, VHFHSZ, SB 9 |
| 2126-005-015 | R1-2-RIO (supplemental district) | 20 / 5 / 15 | 5,517 | 33 | Allowed | Zone conditions, SB 9 |
| 5179-003-026 | Boyle Heights (Chapter 1A) | Stop: code regime not modeled | | | | |
| 4327-028-024 | Beverly Hills | Stop: outside the City | | | | |

**Adversarial checks** (`backend/tests/adversarial/`, `eval/adversarial/`): all pass.
- Regulation text containing injected instructions can produce at most a pending candidate, never a rule.
- An injected "exemption" cannot produce a zero setback.
- Feedback cannot change a rule.
- The extraction schema has no status or confidence field for a model to set.

**Retrieval** (`eval/retrieval/results.md`, 32 questions): recall@5 is 0.781 and MRR is 0.631 with embeddings plus section-id lookup. The question set is small and was written by the search code's author, so treat these numbers as a sanity check.

**Latency**, in process, after warm-up:

| Operation | Runs | p50 | p95 |
|---|---|---|---|
| Full assessment (`assess`) over the 8 golden parcels | 80 | 135 ms | 205 ms |
| Regulation search | 60 | 47 ms | 84 ms |

**Test suites** (2026-10-16): backend 50 passed locally against the loaded database, frontend 7 passed. CI runs the secrets scan, lint, type checks, a production build and the 29 backend tests that need no database. The golden, API and feedback tests need the loaded database, which can't go into CI (it holds hand-saved regulation text), so they skip there and must be run locally.

## AI disclosure
This tool uses an LLM only at ingestion, to extract candidate rule fragments from regulatory text. Explanations are fixed templates, and no model runs when an assessment is requested. Values that rest on unreviewed AI readings are labeled "Interpretation" in the UI. See `AI_USAGE.md` for what was generated and what was independently verified.

## Development

Requirements: Python 3.13 with `uv`, Postgres 16 with PostGIS and pgvector, Node 22.

### API

```sh
cd backend
cp ../.env.example .env            # set DATABASE_URL; secrets come from the environment, never the repo
uv run python -m app.api.auth      # prints a scrypt hash for ADMIN_PASSWORD_SCRYPT (rule review sign-in)
uv run uvicorn app.api.main:app --no-access-log --port 8000
```

`--no-access-log` matters: the default access log prints query strings, which hold addresses.

### Web app

```sh
cd frontend
npm ci
npm run dev        # http://localhost:5173, proxies /api to :8000 (override with API_URL)
npm test           # unit tests
npm run build      # typecheck + production build into frontend/dist
```

Vue 3 + TypeScript + MapLibre, styled with the Forge design tokens (`frontend/src/tokens.css`).
Two pages: the assessment (`/?q=<APN or address>`) and rule review (`/review`, admin sign-in).
The map draws County parcel outlines and Microsoft building outlines (attributed), with no basemap tiles, so no third-party tile host is contacted.
Admin credentials are held in memory for the session and never written to browser storage.


### Running with Docker

```sh
cp .env.example .env                 # set POSTGRES_PASSWORD and the admin values
docker compose up -d --build         # db (PostGIS + pgvector), api, web on http://localhost:8080
docker compose exec api python -m app.db.migrate
```

The database starts empty. Load it either way:

- **From a dump** of a loaded database: `scripts/db-dump.sh regengine.dump` on the source machine, then
  `scripts/db-restore.sh regengine.dump`. The dump contains regulation text saved by hand, so it stays out of git.
- **From the sources**: run, inside the api container, `python -m app.ingest.load_datasets`,
  `python -m app.ingest.regtext.ingest`, `python -m app.search.index` and `python -m app.extract.extract`.
  The regulation text step needs the hand-saved files in `data/manual/` mounted into the container (the image
  does not include them), and extraction needs `ANTHROPIC_COVER_API_KEY`, which compose does not pass by default.
  A fresh extraction creates new candidate ids, so the 2026-10-15 review in `data/verification/` won't apply to
  them: every value stays "Interpretation" until the new candidates are reviewed. Use the dump to reproduce the
  demo exactly.

The api image includes the embedding model, so containers never download it at runtime. Builds behind a
TLS-inspecting proxy can pass that proxy's CA bundle as the build secret `extra_ca`.
