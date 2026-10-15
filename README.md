# Home Building Regulatory Engine (proof of concept)

Decision support for licensed architects and engineers. Given a City of Los Angeles parcel (APN or address), the engine reports which zoning constraints apply to a single-family home, an ADU/JADU, or a guest house, and why. Every claim is tied to the regulatory text it came from and labeled by how it was established.

**This is not a zoning determination.** Outputs must be reviewed by a licensed professional and confirmed with the jurisdiction before they are relied on or shared with a client. Parcel geometry from the County carries its disclaimer: not for legal, engineering, or surveying use.

> Status: under construction. Sections marked _TBD_ are filled in as the work lands.

## What it does
_TBD_

## What it does NOT do
- It does not cover jurisdictions outside the City of Los Angeles. Such parcels get an explicit "outside City of Los Angeles" result.
- It does not model LAMC Chapter 1A (the new Zoning Code, in effect in the Downtown and Boyle Heights Community Plan Areas). Those parcels get a "code regime not modeled" result.
- It models only the R1 zone family. Hillside Area, R1 Variation Zones, HPOZs, specific plans, the Coastal Zone, fire hazard zones, SB 9, and the January 2025 fire rebuild orders are detected and flagged, not applied.
- Setback and buildable-area geometry is illustrative, not survey-grade.
- It does not consider private covenants (CC&Rs), demographic data, or owner information.

## Known constraints
Places where a project guardrail overrides a requirement in the brief. The brief is paraphrased, not quoted.
_TBD_

## Data sources and licenses
See `LICENSES.md` for code dependencies and `backend/app/ingest/sources.yaml` for every dataset and document, with its license, item id, and retrieval date.

## Measured results
_TBD_ (golden tests, adversarial evaluation, latency)

## AI disclosure
This tool uses an LLM to extract rule fragments from regulatory text and to write explanations. Every AI-produced output is labeled in the UI. See `AI_USAGE.md` for what was generated and what was independently verified.

## Development
_TBD_
