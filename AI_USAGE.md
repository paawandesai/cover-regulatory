# AI usage

## Coding assistant
This repository is written with Claude Code (Anthropic) working with the developer. Commits made with it carry a `Co-Authored-By` trailer. Code is reviewed and tested before it is merged, and anything not independently verified is listed below.

## Model used by the application
Configured by `LLM_MODEL_ID` (Anthropic API). The model id and version are recorded on every extraction run and every explanation.

## Model-generated artifacts not independently verified
| Artifact | Produced by | Verified? |
|---|---|---|
| Rule fragments in `rule_fragment` (224 candidates from 11 section groups, 2026-10-15) | `claude-opus-5-5` via the Anthropic API, prompt `extract-v1`; the served model id is stored per run in `extraction_run.served_model` | Partly. A deterministic check confirms each quote occurs in its chunk and each number occurs in its quote. No fragment is used until a person approves it; none approved yet |
| Retrieval question labels in `eval/retrieval/questions.yaml` | Claude Code (the coding assistant), from the ingested text | No. Pending spot-check by Paawan |
| LAMC chunk boundaries and section ids (`chunk_lamc`) | Code written with Claude Code; ids derived by parsing | Spot-checked on 12.08, 12.21 C.10 and 12.22 A.33 only |
