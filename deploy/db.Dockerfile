# Postgres 16 with pgvector (base image) plus PostGIS from the PGDG repository the base image already uses.
FROM pgvector/pgvector:0.8.1-pg16-bookworm
# Optional build secret "extra_ca": for builds behind a TLS-inspecting proxy that only allows HTTPS,
# apt switches to HTTPS and trusts that CA. Normal builds use the image's apt sources unchanged.
RUN --mount=type=secret,id=extra_ca \
    opts=""; \
    if [ -f /run/secrets/extra_ca ]; then \
      sed -i 's|http://|https://|g' /etc/apt/sources.list.d/*; \
      install -m 644 /run/secrets/extra_ca /tmp/extra_ca.crt; \
      opts="-o Acquire::https::CAInfo=/tmp/extra_ca.crt"; \
    fi; \
    apt-get $opts update \
 && apt-get $opts install -y --no-install-recommends postgresql-16-postgis-3 \
 && rm -rf /var/lib/apt/lists/* /tmp/extra_ca.crt
