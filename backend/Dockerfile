FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH FASTEMBED_CACHE_PATH=/opt/fastembed PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml uv.lock ./
# Optional build secret "extra_ca": a CA bundle for builds behind a TLS-inspecting proxy.
RUN --mount=type=secret,id=extra_ca \
    if [ -f /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY migrations ./migrations
COPY data/verification ./data/verification

# Bake the embedding model into the image so the container never downloads it at runtime.
RUN --mount=type=secret,id=extra_ca \
    if [ -f /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca REQUESTS_CA_BUNDLE=/run/secrets/extra_ca; fi; \
    python -c "from fastembed import TextEmbedding; TextEmbedding('nomic-ai/nomic-embed-text-v1.5')"

RUN useradd --system --uid 10001 app && chown -R app /opt/fastembed
USER app
EXPOSE 8000
# --no-access-log: the default access log prints query strings, which hold addresses.
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers"]
