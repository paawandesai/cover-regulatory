# Licenses

License audit output for every dependency, regenerated with `pip-licenses` (backend) and `npx license-checker --summary` (frontend) before each push and before submission.

## Runtime dependencies
None yet (repository scaffold only).

## Development tooling (not linked into the app)
| Tool | License | Use |
|---|---|---|
| gitleaks 8.28.0 | MIT | Secret scanning (pre-commit hook and CI) |
| pre-commit 4.7.0 | MIT | Git hook runner |

## Server processes (separate from the app)
To be recorded as they are added (PostgreSQL, PostGIS (GPLv2, separate server process), Langfuse).

## Data
Dataset and document licenses are recorded in `backend/app/ingest/sources.yaml` and summarized here once they are ingested.
