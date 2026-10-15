# AI usage

## Coding assistant
This repository is written with Claude Code (Anthropic) working with the developer. Commits made with it carry a `Co-Authored-By` trailer. Code is reviewed and tested before it is merged, and anything not independently verified is listed below.

## Model used by the application
Configured by `LLM_MODEL_ID` (Anthropic API). The model id and version are recorded on every extraction run and every explanation.

## Model-generated artifacts not independently verified
| Artifact | Produced by | Verified? |
|---|---|---|
| Rule fragments in `rule_fragment` (230 candidates passing the deterministic checks, 2026-10-15) | `claude-opus-5-5` via the Anthropic API, prompt `extract-v1`; the served model id is stored per run in `extraction_run.served_model` | Partly. A deterministic check confirms each quote occurs in its chunk and each number occurs in its quote. The **review decisions are AI-made, not a person's** (see below) |
| Review decisions on all 230 candidates (222 approved, 8 rejected) | Three-way verification on 2026-10-15: Claude Opus 5.5 against the source chunk, Claude Sonnet 5.5 independently, and web research against official sources (`backend/data/verification/2026-10-15.json`). Applied with `python -m app.extract.apply_review` at the project owner's (Paawan's) instruction | No human has checked these decisions candidate by candidate. Each is recorded with `reviewed_by = 'ai-review'` and a note saying so, and the source panel says "Approved in an AI review" wherever such a rule is used |
| Retrieval question labels in `eval/retrieval/questions.yaml` | Claude Code (the coding assistant), from the ingested text | No. Pending spot-check by Paawan |
| LAMC chunk boundaries and section ids (`chunk_lamc`) | Code written with Claude Code; ids derived by parsing | Spot-checked on 12.08, 12.21 C.10 and 12.22 A.33 only |
