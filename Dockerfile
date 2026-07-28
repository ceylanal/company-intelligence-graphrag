# Multi-stage production Dockerfile for Company Intelligence GraphRAG
# Stage 1: Build virtual environment with uv
FROM python:3.12-slim AS builder

# Set environment variables for build efficiency
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Copy uv binary directly
COPY --from=ghcr.io/astral-sh/uv:0.8.14 /uv /uvx /bin/

# Copy configuration files for dependency resolution
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Sync dependencies into virtual environment
RUN uv sync --frozen --no-dev

# Stage 2: Runtime image
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    ENVIRONMENT=production \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

WORKDIR /app

# Install runtime utilities (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Copy virtualenv and application code from builder stage
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /app/src /app/src
COPY --from=builder --chown=appuser:appgroup /app/pyproject.toml /app/pyproject.toml
COPY --chown=appuser:appgroup README.md /app/README.md
COPY --chown=appuser:appgroup config /app/config

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["sh", "-c", "exec uvicorn company_graphrag.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
