# One-off restore task for AWS (infra/aws/restore.sh): copies a dump from the private data bucket and loads it,
# as scripts/db-restore.sh does for the compose database.
FROM postgres:16-bookworm
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends awscli ca-certificates > /dev/null \
    && rm -rf /var/lib/apt/lists/*
COPY restore-keeping-live-data.sh /usr/local/bin/restore-keeping-live-data.sh
USER postgres
WORKDIR /tmp
# DATABASE_URL, DATA_BUCKET and DUMP_KEY come from the task; PGPASSWORD from Secrets Manager.
ENTRYPOINT ["sh", "-c", "set -e; test -n \"$DUMP_KEY\"; aws s3 cp --quiet \"s3://$DATA_BUCKET/$DUMP_KEY\" /tmp/regengine.dump; sh /usr/local/bin/restore-keeping-live-data.sh /tmp/regengine.dump; rm -f /tmp/regengine.dump"]
