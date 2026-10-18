# Home Building Regulatory Engine (proof of concept)

Decision support for licensed architects and engineers. Given a City of Los Angeles parcel, or one in unincorporated LA County's Zone R-1 (APN or address), the engine reports which zoning constraints apply to a single-family home, an ADU/JADU, or a guest house, and why. Every claim is tied to the regulatory text it came from and labeled by how it was established.

**This is not a zoning determination.** Outputs must be reviewed by a licensed professional and confirmed with the jurisdiction (the City or the County) before they are relied on or shared with a client. Parcel geometry from the County carries its disclaimer: not for legal, engineering, or surveying use.

> Status: proof of concept, built 2026-10-15. The database holds five small, self-selected study areas (Reseda, Boyle Heights, Pacific Palisades and a Westside strip on the Beverly Hills edge in the City, and Del Aire in unincorporated LA County; `backend/app/ingest/study_areas.yaml`), so parcels outside them return "not found". Hosted demo (invite only): https://34-213-114-35.sslip.io. Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## For reviewers
1. Open the hosted demo at https://34-213-114-35.sslip.io. The invite code is sent separately by the project owner; it is not in this repo.
2. Try these APNs (or a street address inside the study areas):
   - **2121-005-008** (Reseda): a vacant flat-land R1 lot where every envelope value is derived (its ADU height near transit and SB 9 result are interpretations).
   - **2104-024-009** (Reseda): a built-up lot with an existing home, its building outline, and the attached ADU raised to 850 sq ft.
   - **2121-003-007** (Reseda): a through lot, so the rear yard is an interpretation.
   - **4412-014-028** (Pacific Palisades): Hillside, Coastal Zone, fire hazard zone and the 2025 fire. The Hillside yards, height, slope-band floor area and lot coverage are applied; the height and floor area are interpretations, the City ADU path is an interpretation, and SB 9 is suspended.
   - **4142-004-002** (Del Aire, unincorporated LA County, Zone R-1): the County's Title 22 yards, height and lot size, all interpretations because the edition of the copy loaded is not stated.
   - **2118-015-001** (commercial zone), **5179-003-026** (Boyle Heights, Chapter 1A) and **4327-028-024** (Beverly Hills): three stop states.
3. Click any value to see the regulation text behind it. Fill in **Your project** (height, floor area, a second unit) to check a design against the limits; the side yard and the drawn buildable area follow the height you enter.
4. **Rule review** (`/review`) needs the admin login, also sent separately. It shows each AI-read rule candidate with its source quote and checks, and the feedback queue. After 10 wrong passwords or invite codes in 15 minutes, that address is blocked for the rest of the window; feedback is limited to 30 notes an hour, chat to 30 questions, assessments to 600 and searches to 300 an hour per address. The limits key on a salted hash of the address, which is never logged.
5. To run it yourself, see Development below. The database dump that reproduces the demo exactly is shared on request, because it contains regulation text saved by hand.

## What it does
Enter an APN or a street address. The engine:

1. **Finds the parcel and stops early when it must.** Outside both the City and unincorporated County, under Chapter 1A, in a County zone other than R-1, or in a zone that is not modeled (anything but R1, R2 and RE9 to RE40, so RD, R3 and the other multiple-dwelling zones) each gets an explicit result instead of wrong rules.
2. **Reports the R1 envelope:** front, side and rear yards, maximum residential floor area, height, and whether the lot meets the R1 minimums, plus an estimate of the block's prevailing front yard and, on a key lot, the averaged front yard it may use (LAMC 12.08 C.1).
   **R2** (LAMC 12.09) lots get the R1 yards (12.09 C.1-C.3 refer to them), 33 ft, how many homes the lot allows (two at most, 2,500 sq ft each, no two-family dwelling under 4,000 sq ft), floor area of three times the buildable area (12.21.1 A.1, an interpretation because the buildable area is measured on the fitted outline) and the R2 lot minimums; SB 9 does not apply in R2. **RE9 to RE40** (LAMC 12.07.01) lots get their own front and rear yards (20% and 25% of depth, at most 25 ft), side yards by designation, 33 or 36 ft, a floor area of 40% or 35% of the lot, the lot minimums and the 20,000 sq ft guest house minimum. Only flat lots in Height District 1 are modeled for R2 and RE: in a Hillside Area, the Coastal Zone or another height district their yards, height and floor area are withheld.
3. **Reports what can be built besides the house:** a detached ADU under state law (800 sq ft) and under the City ordinance (up to 1,200 sq ft), an attached ADU (at least 850 sq ft, which state law says can't be refused), a JADU (500 sq ft), and a guest house (allowed only on lots of 10,000 sq ft or more). It also gives the detached ADU height the City must allow: 16 ft, or 18 ft (plus 2 ft for a matching roof pitch) near frequent transit.
4. **Applies the area rules it models and flags the rest.** Hillside Area lots get the LAMC 12.21 C.10 yards, height by height district (Table 12.21 C.10-4), lot coverage, and floor area from slope bands (Tables 12.21 C.10-2a/2b, with the guaranteed minimum); the slope bands are estimated from USGS elevation, so that floor area is an interpretation. R1V, R1F and R1R variation zones get their own floor area ratio, height and lot coverage (Tables 12.08 C.5(b)-(d)); R1H variation zones use their Hillside column. Coastal Zone lots off the Hillside Area in Height District 1 get 45 ft and three times the buildable area (LAMC 12.21.1). Still flagged, not applied: Hillside grading, parking, fire protection and street access; Very High Fire Hazard Severity Zone rules; overlay plans other than the one below; and zone conditions. The West LA Transportation Improvement and Mitigation Specific Plan (574 loaded residential lots) is read in full (an AI reading not yet checked by a person; see `AI_USAGE.md`): it is a transportation fee and sets no yard, height or floor area rules, so the zone's values stay Derived and an item says when the fee applies (new homes) and what is exempt (additions with no new unit, ADUs). A [Q], [T] or D condition is flagged with what LAMC 12.32 G lets it do (a D can only lower height or floor area, so those values are upper limits); the parcel's own ordinance is not loaded. Coastal Zone lots outside Height District 1 have their floor area and height withheld. Lots that CAL FIRE's 2025 map would newly place in a Very High zone are flagged until the City adopts it. Height Districts 1-L, 1-VL, 1-XL and 1-SS apply their own limits from LAMC 12.21.1 A.1; 1-SS caps the house at one story and 18 ft. Side yards are shown for a house at the maximum height (LAMC 12.08 C.2(b) adds 1 ft per 10 ft above 18 ft), with the table by height in the explanation.
   **SB 9** (Gov. Code 65852.21, 66411.7): up to two homes on the lot and whether it can be split into two lots (each at least 40% of the lot and 1,200 sq ft), with the 800 sq ft and 4 ft setback protections. The engine checks the zone, HPOZ, fire hazard, earthquake fault and flood layers, and lists what it can't check (tenant history, rent control, the Gov. Code 65913.4(a)(6) sites with no loaded map, such as farmland, wetlands and conservation easements), so a "yes" is an interpretation. Inside the Palisades Fire area's Very High fire zone, Executive Order 9 makes SB 9 unavailable.
   **Unincorporated LA County, Zone R-1** (Title 22, wave 9): front, side and rear yards (20, 5 and 15 ft, Table 22.18.040-A), the narrow-lot side yard (10% of the width, at least 3 ft, under 50 ft wide) and shallow-lot rear yard (20% of the depth, at least 10 ft, under 75 ft deep) from 22.110.080, the 35 ft height (22.18.040 B.1) and the required lot area (5,000 sq ft, or the number in the zone, such as R-1-7500; 22.110.130). ADUs and JADUs follow state law, which binds the County as it does the City, and the County's own ADU ordinance (Ord. 2025-0029, Section 22.140.640, adopted 2025-07-29) adds a larger ADU (up to 1,200 sq ft and 25 ft tall, 4 ft from the rear and side lot lines) and, in a Very High Fire Hazard Severity Zone, its two-access-road rule. Those County ADU values are interpretations: HCD's review letter of 2025-12-01 found parts of the ordinance out of line with state law, and state law applies where it allows more. SB 9 applies with the County named. Community Standards Districts, Setback Districts and Hillside Management Areas are detected and flagged. Del Aire lies in the South Bay Planning Area Standards District (Chapter 22.318, adopted 2025-03-11, loaded from the County's ordinance), which includes the Del Aire Community Standards District; it is flagged with its front fence and wall heights, landscaping, lighting and accessory commercial unit rules, and it sets no R-1 yards or height. Title 22 was read from a copy the project owner supplied whose edition is not stated (it uses the 2019 numbering and still says "second units"), so every Title 22 value is an interpretation to confirm with the County, even where its rule was approved. Other County zones get "zone not modeled".
   **Fire rebuild** (Mayor's Emergency Executive Orders 1 and 8, inside the January 2025 fire perimeter): the like-for-like footprint, 110% of the building outlines on the lot (Approximate, since the outline's imagery date is unknown), and in the Coastal Zone the 33 ft height for a zoning-compliant EO 8 rebuild.
5. **Labels every value** with how it was established:
   - **Verified parcel data:** read from a named dataset with its fetch date.
   - **Derived from rule:** computed from regulation text that a review approved (in this demo, an AI review; see Known constraints).
   - **Interpretation, confirm with City:** computed from text that an AI read but no review has approved yet (it shows how many of the rule's inputs were found), or a standard R1 value where something not modeled may change it: a conditioned zone, a specific plan or HPOZ whose text is not loaded, a through lot, a front taken on the long side, or the City ADU on a Hillside lot in a Very High Fire Hazard Severity Zone.
   - **Not modeled here:** a flag makes the flat-land rule wrong (see item 4). No number is shown.
   - **Approximate:** machine-learned building outlines, and lot width and depth fitted to the parcel outline. Shown for context; not survey-grade.
   - **Flag, not evaluated:** a condition detected from a map layer or the zone string (with the layer's fetch date), The engine does not evaluate it.
   - **No cited source:** an input is missing or the rule doesn't apply. No number is shown.
6. **Shows the source.** Clicking any value opens the regulation text with the supporting quote highlighted, plus a link to the official source. State-law citations link to the exact Government Code section on leginfo, and PDF sources open at the cited page.
7. **Draws the lot.** A diagram or map shows the lot and the buildable area left after yards. It is labeled illustrative, not survey-grade. Clicking a yard, the buildable area, an existing building or the lot outline opens the value and its source text.
8. **Takes feedback without letting it change anything.** "Report a problem" queues a note for a reviewer. Feedback never changes a rule. A rule changes status only through a review decision: the password-protected Rule review screen (`/review`), or the `apply_review` command that applied this demo's AI review. A person's re-review of rules the AI review already decided is recorded from the review sheet with `python -m app.extract.human_review <sheet.csv> --reviewer "<name>"`, under that person's name, with the earlier AI decision kept in the audit log. A reviewer can open the rules behind a reported value straight from the Feedback tab.

9. **Answers in one paragraph and checks a project.** A summary states what can be built, how many values need confirming, and the choices to weigh (state or City ADU, guest house or ADU, fire rebuild order or standard rules). Optional project inputs (house height, floor area, a second unit and its size and bedrooms) are checked against the limits, and each check carries the label of the value it was checked against. Optional floor-area details (required covered parking and where it sits, small detached buildings, area under ceilings over 14 ft) apply the LAMC 12.03 exemptions, and a side-wall length checks the plane-break rule.

10. **Saves scenarios and compares them.** Up to four sets of project inputs per parcel are saved in your browser only (nothing is stored on the server) and can be compared side by side.
11. **Makes a client report a reviewer signs.** "Create a report for sign-off" freezes the assessment and the project into a report with every value's label and sources, the disclaimers and the AI disclosure. Its link shows only "Awaiting sign-off" until a reviewer signs it with their name and license number in Rule review (Client reports tab); the signed report prints or saves as PDF. Only the APN is stored, never a typed address.
12. **Answers follow-up questions from cited text.** "Ask a follow-up" sends the question to Claude with this assessment's values and the regulation chunks retrieved for it. The server never adds the APN or address, and scrubs anything shaped like an APN from the question, but a street address the user types into the question is sent as typed. Each sentence of the answer must quote a chunk verbatim or restate an assessment value. The server checks every quote against the chunk, checks every number (in digits or in words) against the quotes and values, and removes any sentence that fails, showing how many were removed. A sentence with no quote is never shown in the model's words: it is rewritten from the values it names ("Rear yard: 15 ft."). A sentence that says something is exempt, waived, reduced, eliminated or does not apply must reproduce the quote that says so. The form says, before you ask, that the question goes to Anthropic's model as typed. The question is not logged or stored. The chat answers about this parcel's assessment and the loaded regulation text; it does not query the dataset as a whole (it can't answer "how many R1 lots are loaded").

No AI model runs when you ask for an assessment. The AI work happens once, at ingestion: a model reads the regulation text into candidate rule fragments, each with a verbatim quote. A deterministic check rejects any fragment whose quote is not in the text or whose number is not in the quote. Answers are therefore repeatable and fast.

## What it does NOT do
- It covers the City of Los Angeles and Zone R-1 in unincorporated LA County. Parcels in the other 87 cities get an explicit "outside City of Los Angeles" result. In the County, only Zone R-1 is modeled, from a Title 22 copy of unstated edition; Community Standards Districts elsewhere in the County (Title 22 Volume II) and Setback Districts are flagged but not applied, and guest house uses are not modeled; no Volume II district or Setback District covers the loaded Del Aire lots. The County ADU ordinance's unit counts, conversions and scenic-route height cap are stated or named, not computed. The County's GIS layers have no corner-lot flag, so corner lots are read from the parcel map: a lot is a corner lot when two of its sides face streets, and a reversed corner lot when the lot behind it fronts its side street. That reading gets the street side yard (5 ft, or 10 ft on a reversed corner lot) and is marked as an interpretation.
- It models only a small part of LAMC Chapter 1A (the new Zoning Code, in effect in the Downtown and Boyle Heights Community Plan Areas). Those parcels still get a "code regime not modeled" result, with no Chapter I rules, plus their zone string split into its five districts (Article 1) and the number of homes their Density District allows (Article 6, for example 2 per lot in 2L, or one per 1,500 sq ft in 15). Form, frontage, development standards, use and the CPIO (Articles 2 to 5) are not loaded, so no envelope is shown.
- It models the R1 zone family (with its Hillside, Coastal Zone and variation rules) and flat R2 and RE lots in Height District 1. RS, RD, R3 and the other multiple-dwelling zones are not modeled. HPOZs, specific plans, fire hazard zone rules, and Hillside grading and access rules are detected and flagged, not applied.
- Hillside floor area depends on slope bands estimated from the USGS 3DEP elevation model on a grid of about 3 ft; the City requires a surveyed slope analysis map, which can differ. A Hillside lot with no slope estimate has its floor area withheld.
- The fire hazard zone applied is the City's current map (LA GeoHub). CAL FIRE's 2025 recommended map is loaded for comparison; in the loaded areas it adds no City lots.
- Setback and buildable-area geometry is illustrative, not survey-grade.
- It does not consider private covenants (CC&Rs), demographic data, or owner information.
- Existing buildings are shown as approximate Microsoft machine-learned outlines (ODbL). They can miss, merge or misplace buildings. The Assessor's building attributes are shown when recorded.
- The follow-up chat answers only from the loaded regulation text and this assessment's values. A question the loaded text doesn't answer gets "does not answer this", not a guess. It needs `ANTHROPIC_COVER_API_KEY` on the server; without it the chat says it is turned off.
- A client report opens only after a licensed reviewer signs it in Rule review. The report is a frozen copy: it does not update when rules or data change. Reports are deleted with feedback after `FEEDBACK_RETENTION_DAYS` (1 day on the hosted demo).
- The fire rebuild results use the Mayor's Emergency Executive Orders 1 (revised 2025-03-18), 8 and 9 as published on the Mayor's Emergency Orders page. Orders change; check the current order. The engine cannot see what stood on a lot before the fire, so the like-for-like footprint is scaled from today's building outlines and the height limit is stated in words.
- SB 9 results depend on facts outside the loaded data (tenants, rent control, Ellis Act withdrawals) and on the site exclusions of Gov. Code 65913.4(a)(6)(B)-(K) as that section read on 2021-09-16. The copy loaded is the official text in effect since 2026-01-01 (as amended by SB 597, Stats. 2025, Ch. 774), read from the Legislative Counsel's leginfo download with `scripts/leginfo-section.py`; its (B)-(K) list the same kinds of site, but the wording may differ from 2021. Only the fire, fault and flood exclusions ((D), (F), (G)) have a loaded map. They are interpretations, except where SB 9 is ruled out (Executive Order 9, or a lot too small to split).
- An address that matches no County address point or parcel situs is sent to the US Census Geocoder (a public, no-account service). APN searches never leave the server.
- The prevailing front yard and the key-lot front yard are estimates from parcel outlines and machine-learned building outlines, labelled Approximate and listing the lots they counted; confirm them on a survey. The per-story side-yard rule in the Coastal Zone is named but not computed.
- The 18 ft ADU height near transit uses Caltrans' straight-line half-mile transit areas. The law counts walking distance, so inside an area the 18 ft is an interpretation to confirm; outside every area the 16 ft is certain.
- Corner lots are detected only where two adjacent sides read as streets on the parcel map. When only the long side reads as a street, the front and side yards are labelled as interpretations.

## Known constraints
Places where a project guardrail overrides a requirement in the brief. The brief is paraphrased, not quoted.

| The brief asks for | What this tool does instead, and why |
|---|---|
| Cutting regulatory research effort to zero | It cuts the time to a **validated** answer. It is decision support: a licensed professional reviews the cited output and confirms with the City. "Zero" is neither safe nor measurable. |
| Real-time answers as inputs change | "Real-time" has no target in the brief, so it can't be measured as stated. What is measured instead: assessment latency over the golden parcels, in process and over HTTP (`python -m app.engine.benchmark`, `eval/latency.md`), and no model call on the assessment path. |
| Possibly GCP for geocoding | No Google services. The APN path needs no geocoder. Addresses resolve through County address points, then County parcel situs, then the US Census Geocoder (public domain). |
| The latest AI technology | A generally available model, pinned by id in configuration (`LLM_MODEL_ID`), used at ingestion and in the optional follow-up chat, never to compute an assessment. |
| A specific frontend, AI framework or model provider (the brief leaves these open or only suggests them) | Vue 3 (one of Cover's own listed technologies), the Anthropic SDK called directly, and Anthropic models. The pipeline is a handful of fixed calls with schema-validated output, so an orchestration framework would add dependencies without adding a control. |
| Testing on parcels Cover would provide | None were delivered. The golden cases are **self-selected** parcels (vacant or City-owned where possible), identified by APN only. |
| More specific resources from Cover | None were invented. Sources are official City, County and State publications, with two exceptions listed in the next row. |
| Regulation text from official sources only (guardrail) | **Unresolved for any use beyond this demo.** Two texts come from publisher sites, saved or supplied by hand, never crawled: LAMC Chapter I from American Legal Publishing's free viewer (codelibrary.amlegal.com, now part of ICC, whose terms bar data mining) and LA County Title 22 from a copy the project owner supplied (its recorded source is Municode). Gov. Code 65913.4, first loaded from a FindLaw page, was replaced on 2026-10-17 by the official text from the Legislative Counsel's download. These are the publishers each government names for its official code: the City has no consolidated Chapter I of its own, and the County names Municode as its online publisher (its own planning-site copy of Title 22 is gone; the only full text on a County host is a 2015 draft of Volume I from before the 2019 rewrite, checked 2026-10-18). The only government-hosted alternatives are the individual amending ordinances (City Clerk council files, County Board files), which do not add up to current consolidated text without error-prone reassembly. The enacted text is public law, but these copies were chunked, embedded and read by a model, and they sit in the private database dump. Before any use beyond this demo, license them from the publishers or rebuild the sections the engine reads from the enacting ordinances. No text from either is committed: the browser-test fixtures replace it with synthetic placeholders (`scripts/e2e-fixtures.py`), and downloads are limited to official City, County and State hosts. |
| Two or three rule families in one zone family (guardrail) | Built on the project owner's instruction to do every item on the left-out list: R1, R2 and RE in the City, County R-1, ADU/JADU, guest house, SB 9 and fire rebuild orders, with Hillside, Coastal and variation-zone tables. Breadth went up; every value outside the original R1 scope is labelled by how it was established, and anything not modeled stops or is withheld. |
| Rules approved by a person before use | In this demo the rule candidates were reviewed by AI, at the project owner's instruction: a three-way check (source text, a second model, official sources) decided each of the 230 candidates on 2026-10-15 (8 rejected). On 2026-10-16 ZA Memo 143 Revision 1 replaced the original memo; its 40 earlier decisions were retired and 33 re-extracted candidates were decided the same way (2 rejected). Later waves added more rules the same way (634 approved in all). On 2026-10-17 the project owner was sent the 356 approved rules the engine reads (the review sheet's "Used in assessments" tab, each with its quote and link) and approved them in bulk, in one decision, rather than rule by rule; that approval is recorded under his name with `app.extract.human_review` (`backend/data/verification/2026-10-17-paawan-review.csv`), and the source panel names the approver ("Approved by Paawan"). The review sheet and its one-decision approval are what that name stands for. The other 278 approved rules still rest on the AI review alone (see `AI_USAGE.md`). Most are table cells no loaded lot reads, but six were added after that review and are read: the County ADU rules from Ord. 2025-0029, whose values are labelled Interpretation. |
| Feedback that improves future answers | Feedback is queued for a reviewer and never edits rules, prompts or retrieval automatically. |
| An admin interface that adjusts the system | Rule review approves or rejects rule candidates, handles feedback, signs client reports, and shows the source checks and the audit log. It has no settings to change thresholds, toggle rules or re-run the pipeline; those are code and command-line steps (`app.extract.extract`, `app.ingest.regtext.refresh`), so every change is reviewed in git. |
| Scaling to LA County, California and beyond | LA City (Chapter I: R1, R2, RE) and unincorporated LA County Zone R-1 are implemented. The County was added as a second jurisdiction on the same data flow (its own zoning layer, boundary, zone parser and rules); `ARCHITECTURE.md` lists what it took, what a further jurisdiction needs, and what changes outside California (the state-law layer). Nothing outside LA County is built. |
| Developing on synthetic data only, with a "Demo — synthetic data only" banner (guardrail) | The brief asks for public parcel and zoning data, so the engine uses real public County and City layers with owner fields dropped at ingestion. Fixtures are APNs only, with no addresses. Because "synthetic" would be untrue, the hosted banner reads "Hosted demo with public data only. Please don't enter personal information." The project owner approved this wording on 2026-10-16. |
| Store only APN, geometry, use code, lot dimensions, zoning, overlays and footprints (guardrail) | Parcels also keep the County roll's situs address (house number, street, city, ZIP), needed to find a parcel by address, and its building attributes (year built, units, bedrooms, bathrooms, building area), needed for the existing-home floor area and the attached ADU limit. Owner name, mailing address, exemption flag and sale amount are never requested. The browser-test fixtures carry those building attributes for a few APNs. |
| LA City Parcels and Zoning from the CC0 copies on data.gov (guardrail) | Parcels come from the County Assessor's open layer (the City layer has no lot attributes), and zoning from City Planning's live layer under its web terms, because the data.gov copy dates to April 2024. Both are recorded with item id and fetch date in `backend/app/ingest/sources.yaml`. |
| Chat answers that cannot assert what the text does not say (guardrail) | The server keeps a chat sentence only if its quotes are verbatim in a loaded chunk or it restates assessment values, every number comes from those, and any wording that lifts a requirement (variance, exempt, waived, not required, does not apply) is in its own quotes. The surrounding wording is still the model's, and a quote taken out of context can still mislead, so the chat is labelled AI-generated and is not part of the signed report. |
| Secrets never in Terraform state (guardrail) | The database password is write-only and app secrets live in Secrets Manager, but the random header CloudFront sends to the ALB (`random_password.origin_verify`) is in state, which is encrypted. It only proves a request came through CloudFront (`infra/aws/README.md`). |
| Visualizing existing buildings | Uses Microsoft's machine-learned footprints (ODbL), kept in their own table and labelled approximate. The County building outlines were not used because their license is unclear. Footprints can miss, merge or misplace buildings. |

## Data sources and licenses
See `LICENSES.md` for code dependencies and `backend/app/ingest/sources.yaml` for every dataset and document, with its license and item id. Retrieval dates are recorded in the `source` table at load time and shown beside each value.

## Measured results
Measured on the development machine (4 CPU cores, no GPU, Postgres on the same machine). Latency and the test counts were measured on 2026-10-18.

**Golden parcels** (`backend/tests/golden/`): all pass. The table shows the original cases; later waves added more, including six in unincorporated LA County. The expected values were calculated by Claude Code (the coding assistant) from the code text and the parcel data, not copied from the engine's output, then compared with the engine. That makes them a check by the same assistant that wrote the engine, not an independent one, and some inputs (the fitted lot width and depth, the slope bands) are the engine's own. The project owner (Paawan) spot-checked a sample against the code text (2026-10-16 for the City, 2026-10-17 for the County; decision D17); no signed sheet of that check is committed. Every value in the table below is asserted, plus each case's status, flags and labels (`backend/tests/golden/cases.yaml`). Side yards are for a house at the maximum height (5 ft + 2 ft for 33 ft).

| APN | Case | Front / side / rear (ft) | Max floor area (sq ft) | Height (ft) | Guest house | Flags |
|---|---|---|---|---|---|---|
| 2121-005-008 | Reseda R1-1, 60 x 135 ft | 20 / 7 / 15 | 3,645 | 33 | Not allowed | SB 9: two homes, lot split |
| 2121-016-012 | Reseda R1-1, exactly 50 ft wide | 20 / 7 / 15 | 2,453 | 33 | Not allowed | SB 9: two homes, lot split |
| 2121-002-004 | Reseda R1-1, 25 ft wide (substandard) | 20 / 5 / 15 | 1,462 | 33 | Not allowed | SB 9: two homes, lot split |
| 4359-016-023 | R1-1, 16,403 sq ft, in the West LA transportation plan | 20 / 7 / 15 | 7,381 | 33 | Allowed | Transportation fee plan; SB 9: two homes, lot split |
| 4412-014-028 | Pacific Palisades, Hillside + Coastal + fire | 20 / 5 / 15 (+1 ft per story above two) | 4,272 (slope bands, interpretation) | 33 (interpretation) | Allowed | Fire rebuild, Hillside, Coastal, VHFHSZ; SB 9 not available (EO 9) |
| 2126-005-015 | R1-2-RIO (supplemental district, interpretation) | 20 / 7 / 15 | 5,517 | 33 | Allowed | Zone conditions; SB 9: two homes, lot split |
| 2104-024-009 | Reseda, existing home; front on the long side (interpretation) | 12 / 7 / 15 | 3,168 | 33 | Not allowed | SB 9: two homes, lot split |
| 2121-003-007 | Reseda, existing home; through lot | 20 / 7 / 15 (rear: interpretation) | 9,113 | 33 | Allowed | SB 9: two homes, lot split |
| 4359-015-009 | RE20-1, 24,208 sq ft, in the West LA transportation plan | 25 / 10 / 25 | 8,473 | 36 | Allowed | Transportation fee plan; SB 9: two homes, lot split |
| 2126-020-001 | R2-1-RIO, 48 ft wide (interpretation) | 20 / 6.8 / 15 | 14,436 (3 x buildable area) | 33 | Not allowed | Two homes allowed by R2; SB 9 does not apply |
| 4411-004-013 | RE15-1 in a Hillside Area | Withheld | Withheld | Withheld | Not allowed | Fire rebuild; SB 9 not available (EO 9) |
| 4412-004-026 | RD2-1 (multiple dwelling) | Stop: zone not modeled | | | | |
| 2118-015-001 | [Q]C2-2D-CDO (commercial) | Stop: zone not modeled | | | | |
| 5179-003-026 | Boyle Heights (Chapter 1A) | Stop: code regime not modeled | | | | |
| 4327-028-024 | Beverly Hills | Stop: outside the City | | | | |
| 4142-004-002 | Del Aire, County R-1, 70 x 85 ft | 20 / 5 / 15 (interpretation) | None in Title 22 R-1 | 35 (interpretation) | Not modeled | SB 9: two homes, lot split |
| 4144-001-012 | Del Aire, County R-1, 40 ft wide | 20 / 4 / 15 (interpretation) | None in Title 22 R-1 | 35 (interpretation) | Not modeled | |
| 4142-004-001 | Del Aire, County R-1, reversed corner lot | street side 10 / side 5 (interpretation) | None in Title 22 R-1 | 35 (interpretation) | Not modeled | |
| 4143-016-041 | Del Aire, County R-1, 59 ft deep, 3,460 sq ft | 20 / 5 / 11.7 (interpretation) | None in Title 22 R-1 | 35 (interpretation) | Not modeled | Below the 5,000 sq ft lot area |
| 4142-007-019 | Del Aire, County R-1 | 20 / 5 / 15 (interpretation) | None in Title 22 R-1 | 35 (interpretation) | Not modeled | Hillside Management Area |
| 4144-001-800 | Del Aire, County R-3 | Stop: zone not modeled | | | | |

**Adversarial checks** (`backend/tests/adversarial/`, `eval/adversarial/`): all pass.
- Regulation text containing injected instructions can produce at most a pending candidate, never an approved rule. A pending candidate can be shown, labelled Interpretation, where no approved reading exists; it never outranks an approved one.
- An injected "exemption" cannot produce a zero setback.
- Feedback cannot change a rule.
- The extraction schema has no status or confidence field for a model to set.
- The same injected text inside a PDF, read through the ingestion PDF reader, is held to the same checks.
- A chat answer repeating a variance that does not exist is removed, in the literal words or in others ("doesn't apply", "an adjustment eliminates the rear yard", "five feet", or a real quote about something else). A sentence with no quote is shown only as the values it names.
- Project inputs, the search box and a report signer's note are data: bad inputs are refused, nothing they say changes a value, and none of it is logged or rendered as HTML.

**Retrieval** (`eval/retrieval/results.md`): on a 50-question holdout written by a second model from sampled chunks (it never saw the search code; it was measured several times during development, so it is not a pristine holdout, though it never moved after a change), recall@5 was 0.56 and MRR 0.44 with embeddings plus section-id lookup on 2026-10-16. On the 32-question dev set that search was tuned on it was 0.81, so the dev number overstates accuracy. On 2026-10-17 they were 0.54 and 0.75: the other zones' sections loaded in wave 7a read like R1's and crowded it out. A query that names a zone now also ranks that zone's own section, which brings the dev set back to 0.81 (MRR 0.70); the holdout, run once afterwards, stays at 0.54. The County text, which a City search leaves out, changes neither. On a 30-question County set written the same way, County-scoped search finds the source section in the top five for 0.77 of questions, against 0.60 unscoped. The holdout counts only the source chunk's section as right, which makes it a lower bound. Assessment values do not depend on search.

**Latency** (`eval/latency.md`, `python -m app.engine.benchmark`), measured 2026-10-18 on the development container (4 CPUs, Postgres on the same machine), over the 18 golden parcels that get an assessment, 10 runs each after a warm-up:

| Operation | Runs | p50 | p95 |
|---|---|---|---|
| Full assessment (`assess`) in process | 180 | 417 ms | 601 ms |
| GET /api/assess over local HTTP | 180 | 419 ms | 601 ms |
| Regulation search (the 32 retrieval questions, 2026-10-16) | 32 | 52 ms | 114 ms |

The hosted demo answered in 0.80 s at p50 (10 calls for 2121-005-008 from a cloud container, 2026-10-18), most of that the network. The assessment took 266 ms (p50) on 2026-10-16, before the County and the wave 7 zones; the prevailing front yard, which reads every lot and building on the block face, is most of the cost.

**Test suites** (2026-10-18): 177 passed: backend 159 (75 unit, 84 against the loaded database), frontend 9, browser 7, and 2 Terraform test runs that apply the AWS setup to mocked providers. CI runs the secrets scan, lint, type checks, a production build, the unit, frontend and browser tests, the Terraform checks, and (job `db-tests`) the golden, API and adversarial suites against the private database dump. Full results: `eval/test-results.md`.

## AI disclosure
This tool uses an LLM at ingestion, to extract candidate rule fragments from regulatory text, and in the optional follow-up chat, whose answers keep only sentences with quotes checked against the source. Explanations are fixed templates, and no model runs when an assessment is requested. Values that rest on unreviewed AI readings are labeled "Interpretation" in the UI. See `AI_USAGE.md` for what was generated and what was independently verified. The chat and extraction use Anthropic's commercial API: under Anthropic's commercial terms, API inputs and outputs are not used to train models, and they are retained only for the period Anthropic's current data-retention policy states (check it before sending anything sensitive; the chat form asks users not to type personal information).

## Development

Requirements: Python 3.13 with `uv`, Postgres 16 with PostGIS and pgvector, Node 22.

### API

```sh
cd backend
cp ../.env.example .env            # set DATABASE_URL; secrets come from the environment, never the repo
uv run python -m app.api.auth      # prints a scrypt hash for ADMIN_PASSWORD_SCRYPT (bootstrap rule review sign-in)
uv run python -m app.api.reviewers add jdoe "Jane Doe"   # a named reviewer account (prompts for a password)
uv run uvicorn app.api.main:app --no-access-log --port 8000
```

`--no-access-log` matters: the default access log prints query strings, which hold addresses. Settings come from the environment first and `.env` second, so a shell that exports `DEMO_INVITE_CODE` turns the invite gate on locally. `LLM_MODEL_ID` has no default in code: without it the chat is off and extraction refuses to run. Set `API_DOCS=true` to serve the Swagger UI at `/api/docs` (off by default, and off on the hosted demo).

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
Admin credentials are held in memory for the session and never written to browser storage. Each reviewer should have a named account (`app.api.reviewers`), so every decision carries their name; the `ADMIN_USERNAME` account is for setting up. The Sources tab shows the weekly source check: downloadable sources are re-fetched, and when one changes, every approved rule whose text changed goes back to review (a rejected one stays rejected), so its value shows as an Interpretation until someone approves it again. Hand-saved sources (LAMC, ZA Memo 143 Revision 1, Gov. Code pages and the Title 22 copy) are never fetched and are listed as due for a hand re-check after 90 days. The Audit log tab lists every approval, rejection, feedback decision, report signature and withdrawal, and account change. A database trigger refuses edits and deletes from the app. The app connects as the table owner, so the owner role could still drop or truncate the table; a production setup would give the app role insert and select only. The log starts with wave 6; decisions before that are recorded only on each rule (`reviewed_by`).


### Running with Docker

```sh
cp .env.example .env                 # set POSTGRES_PASSWORD and the admin values
docker compose up -d --build         # db (PostGIS + pgvector), api, web on http://localhost:8080
docker compose exec api python -m app.db.migrate
```

The database starts empty. Load it either way:

- **From a dump** of a loaded database: `scripts/db-dump.sh regengine.dump` on the source machine, then
  `scripts/db-restore.sh regengine.dump`. The dump contains regulation text saved by hand, so it stays out of git (the browser-test fixtures use synthetic placeholders for LAMC and Title 22 text). The dump leaves out the rows a deployment writes for itself (reviewer accounts, client reports, feedback, source checks), and the restore keeps the ones already in the target database.
- **From the sources**: run, inside the api container, `python -m app.ingest.load_datasets`,
  `python -m app.ingest.regtext.ingest`, `python -m app.search.index` and `python -m app.extract.extract`.
  The regulation text step needs the hand-saved files in `data/manual/` (the LAMC chapter, the Gov. Code pages and
  ZA Memo 143 Revision 1 as `za_memo_143_rev1.pdf`) mounted into the container (the image
  does not include them), and extraction needs `ANTHROPIC_COVER_API_KEY` and `LLM_MODEL_ID` (compose passes both to the api container when they are set in `.env`).
  A fresh extraction creates new candidate ids, so the reviews in `backend/data/verification/` won't apply to
  them: every value stays "Interpretation" until the new candidates are reviewed. Use the dump to reproduce the
  demo exactly.

The api image includes the embedding model, so containers never download it at runtime. Builds behind a
TLS-inspecting proxy can pass that proxy's CA bundle as the build secret `extra_ca`.
