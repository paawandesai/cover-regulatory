#!/usr/bin/env bash
# Dump the local database (parcels, zoning, regulation chunks, embeddings, rule fragments) for loading into
# another environment. The dump holds regulation text saved by hand; keep it out of git and share it privately.
# Rows of the tables a deployment writes for itself (reviewer accounts and their password hashes, client reports and
# their link tokens, feedback, source checks) are left out; restore with deploy/restore-keeping-live-data.sh.
set -euo pipefail
out=${1:-regengine.dump}
pg_dump --format=custom --no-owner --no-privileges --exclude-table-data=feedback --exclude-table-data=reviewer \
  --exclude-table-data=report --exclude-table-data=source_check "${DATABASE_URL:?}" > "$out"
echo "wrote $out"
