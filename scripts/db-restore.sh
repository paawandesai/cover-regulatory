#!/usr/bin/env bash
# Load a dump from scripts/db-dump.sh into the compose database. Run from the repo root.
set -euo pipefail
dump=${1:?usage: scripts/db-restore.sh regengine.dump}
docker compose exec -T db pg_restore --no-owner --no-privileges --clean --if-exists -U regengine -d regengine < "$dump"
