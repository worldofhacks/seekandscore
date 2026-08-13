# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.8.13 AS uv
FROM python:3.13.7-slim-bookworm AS build

COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY python ./python
COPY services ./services
COPY migrations ./migrations
COPY config ./config
COPY scripts/runtime/python-entrypoint.sh ./scripts/runtime/python-entrypoint.sh
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

FROM python:3.13.7-slim-bookworm AS runtime
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates libgeos-c1v5 libpq5 libproj25 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --home-dir /home/app app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
USER 10001:10001
ENTRYPOINT ["/app/scripts/runtime/python-entrypoint.sh"]
CMD ["python", "-m", "seekandscore.worker", "--queues", "acquire,parse,resolve,geo,market,score,deliver"]
