#!/bin/sh
# Restore a regulation-data dump (scripts/db-dump.sh) into $DATABASE_URL without losing the tables that only the
# running deployment writes: reviewer accounts, client reports, feedback and source checks. A plain
# `pg_restore --clean` drops and recreates every table in the dump, and those tables' schemas are in it, so it would
# silently empty them. Their rows are copied out first and loaded back after the restore.
# Used by scripts/db-restore.sh (compose) and deploy/dbtool.Dockerfile (AWS); the demo server should restore the same way.
set -eu
dump=${1:?usage: restore-keeping-live-data.sh regengine.dump}
: "${DATABASE_URL:?}"
tables="reviewer report feedback source_check"
keep=$(mktemp)
trap 'rm -f "$keep"' EXIT
present=$(psql "$DATABASE_URL" -Atc "SELECT string_agg(tablename, ' ') FROM pg_tables WHERE schemaname = 'public'
  AND tablename IN ('reviewer', 'report', 'feedback', 'source_check')")
if [ -n "$present" ]; then
  args=""
  for t in $present; do args="$args --table=public.$t"; done
  # shellcheck disable=SC2086
  pg_dump --format=custom --data-only $args "$DATABASE_URL" > "$keep"
fi
pg_restore --no-owner --no-privileges --clean --if-exists -d "$DATABASE_URL" "$dump"
if [ -s "$keep" ]; then
  psql -q "$DATABASE_URL" -c "TRUNCATE $(echo "$present" | sed 's/ /, /g')"
  pg_restore --data-only --no-owner --no-privileges -d "$DATABASE_URL" "$keep"
  echo "kept rows of: $present"
fi
echo restored
