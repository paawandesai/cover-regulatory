#!/usr/bin/env bash
# Load a database dump (scripts/db-dump.sh) into RDS: upload it to the private data bucket, then run the restore
# task. The dump holds hand-saved regulation text, so it goes only to that bucket, never to a public place.
#   infra/aws/restore.sh /path/to/regengine.dump
set -euo pipefail
cd "$(dirname "$0")"
dump=${1:?usage: restore.sh <dump file>}
key="dumps/$(date -u +%Y%m%dT%H%M%SZ)-$(basename "$dump")"
aws s3 cp --region "$(terraform output -raw region)" --sse AES256 "$dump" "s3://$(terraform output -raw data_bucket)/$key"
./run-task.sh restore "DUMP_KEY=$key"
./run-task.sh migrate
