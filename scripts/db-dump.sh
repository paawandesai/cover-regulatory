#!/usr/bin/env bash
# Dump the local database (parcels, zoning, regulation chunks, embeddings, rule fragments) for loading into
# another environment. The dump holds regulation text saved by hand; keep it out of git and share it privately.
set -euo pipefail
out=${1:-regengine.dump}
pg_dump --format=custom --no-owner --no-privileges --exclude-table-data=feedback "${DATABASE_URL:?}" > "$out"
echo "wrote $out"
