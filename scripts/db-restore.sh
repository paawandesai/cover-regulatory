#!/usr/bin/env bash
# Load a dump from scripts/db-dump.sh into the compose database. Run from the repo root. Reviewer accounts, client
# reports, feedback and source checks already in the database are kept (deploy/restore-keeping-live-data.sh).
set -euo pipefail
dump=${1:?usage: scripts/db-restore.sh regengine.dump}
docker compose cp "$dump" db:/tmp/regengine.dump
docker compose cp deploy/restore-keeping-live-data.sh db:/tmp/restore-keeping-live-data.sh
docker compose exec -T -e DATABASE_URL=postgresql://regengine@/regengine db \
  sh /tmp/restore-keeping-live-data.sh /tmp/regengine.dump
docker compose exec -T db rm -f /tmp/regengine.dump /tmp/restore-keeping-live-data.sh
