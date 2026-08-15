FROM python:3.13-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# The virtualenv lives outside /app so that bind-mounting the source over /app
# during development does not hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./


# The image the test suite runs in, and the one docker-compose.yml builds.
FROM base AS development

# Dev dependencies included: the test suite runs inside this image.
RUN uv sync --frozen

ENV PATH="/opt/venv/bin:$PATH"

COPY . .

EXPOSE 8000


# The image docker-compose.prod.yml builds. Separate from development rather
# than the same image with a different command, so that pytest and its
# dependencies are not shipped to a public host at all.
FROM base AS production

RUN uv sync --frozen --no-dev

ENV PATH="/opt/venv/bin:$PATH"

COPY . .

# A process that does not need to be root should not be. Nothing here writes to
# the filesystem: the database holds the state and the venv is already built.
RUN useradd --create-home --uid 10001 kanban && chown -R kanban:kanban /app
USER kanban

EXPOSE 8000
