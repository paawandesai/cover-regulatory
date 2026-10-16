# AI usage

## Coding assistant
This repository is written with Claude Code (Anthropic) working with the developer, configured for Claude Opus 5.5 (`claude-opus-5-5`, 1M context). Commits made with it carry a `Co-Authored-By` trailer. Code is tested (CI plus the local database suites) before it is merged. Merge requests were merged on the owner's instruction without a separate human code review, and anything not independently verified is listed below.

## Model used by the application
Configured by `LLM_MODEL_ID` (Anthropic API). The model id, the served model and the prompt version are recorded on every extraction run (`extraction_run.model_id`, `served_model`, `prompt_version`). Explanations shown in the app are fixed templates written in code, not model output, and no model runs when an assessment is requested.

## Model-generated artifacts not independently verified
| Artifact | Produced by | Verified? |
|---|---|---|
| Rule fragments in `rule_fragment` (230 candidates passing the deterministic checks, 2026-10-15) | `claude-opus-5-5` via the Anthropic API, prompt `extract-v1`; the served model id is stored per run in `extraction_run.served_model` | Partly. A deterministic check confirms each quote occurs in its chunk and each number occurs in its quote. The **review decisions are AI-made, not a person's** (see below) |
| Review decisions on all 230 candidates (222 approved, 8 rejected) | Three-way verification on 2026-10-15: Claude Opus 5.5 (`claude-opus-5-5`, via Claude Code) against the source chunk, Claude Sonnet 5.5 (`claude-sonnet-5-5`, Anthropic API) independently, and web research against official sources (City Clerk, City Planning, ZA Memo 143) plus a public mirror of the Government Code (california.public.law, because leginfo blocks scripted reads) (`backend/data/verification/2026-10-15.json`). On 2026-10-16 the memo was re-ingested from Revision 1; 33 re-extracted memo candidates were checked by Claude Opus 5.5 and Claude Sonnet 5.5 against Revision 1 itself, and those identical to an earlier candidate carried its decision (`backend/data/verification/2026-10-16-za-memo-143-rev1.json`). Also on 2026-10-16, 14 candidates from the Residential Floor Area definition (LAMC 12.03) were extracted for the floor-area exemptions; Claude Opus 5.5 and Claude Sonnet 5.5 checked each, 11 were approved and 3 Hillside basement candidates were left pending (`backend/data/verification/2026-10-16-rfa-definition.json`). All three were applied with `python -m app.extract.apply_review` at the project owner's (Paawan's) instruction | No human has checked these decisions candidate by candidate. Each is recorded with `reviewed_by = 'ai-review'` and a note saying so, and the source panel says "Approved in an AI review" wherever such a rule is used |
| Retrieval question labels in `eval/retrieval/questions.yaml` | Claude Code (the coding assistant), from the ingested text | No. Pending spot-check by Paawan |
| LAMC chunk boundaries and section ids (`chunk_lamc`) | Code written with Claude Code; ids derived by parsing | Spot-checked on 12.08, 12.21 C.10 and 12.22 A.33 only |
| Golden expected values (`backend/tests/golden/cases.yaml`) | Claude Code, from the code text and the parcel data | Yes. Paawan spot-checked them against the code text on 2026-10-16 (decision D17) |
| Adversarial test document (`eval/adversarial/injected_document.txt`) | Claude Code | Not applicable: synthetic test input |
| Documentation (README, ARCHITECTURE, this file, LICENSES notes) and UI copy | Claude Code | Reviewed against the code in a final audit on 2026-10-16, not line by line by a person |
| Explanation templates in `backend/app/engine/assess.py` | Claude Code, from the regulation text | Checked in the 2026-10-15 three-way verification; six were corrected |
