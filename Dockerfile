# syntax=docker/dockerfile:1.29

# Build stage
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS builder

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock README.md version ./

# Project sources are needed because uv installs the root package itself
COPY src/ ./src/

# Create virtual environment and install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --extra mcp --extra openai --extra anthropic

# Runtime stage
FROM python:3.15-slim@sha256:65a65fc7b30b06cb6df4930fd4650697cb23f4c2698ab81fc87e4b031bc36928 AS runtime

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Copy application code
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser scripts/ ./scripts/

# Writable cache dirs for model downloads (appuser has no $HOME)
ENV HF_HOME=/app/.cache/huggingface \
    XDG_CACHE_HOME=/app/.cache \
    TRANSFORMERS_HOME=/app/.cache/transformers

RUN mkdir -p /app/.cache && chown -R appuser:appuser /app/.cache

# Compile a separate final layer so read-only deployments do not parse the
# dependency source graph on every cold start. Checked hashes remain valid
# after OCI timestamp normalization and reject bytecode for changed sources.
RUN /app/.venv/bin/python -m compileall -f --invalidation-mode checked-hash -q \
    /app/.venv/lib /app/src

# Switch to non-root user
USER appuser

# Set PATH to use venv
ENV PATH="/app/.venv/bin:$PATH"

# Default command
CMD ["energy-rag-api"]
