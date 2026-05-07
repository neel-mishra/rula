FROM python:3.11-slim

# Build argument to toggle dev vs. production extras.
ARG INSTALL_DEV=false

WORKDIR /app

# Install uv for fast, reproducible dependency resolution.
RUN pip install --no-cache-dir uv

# Install dependencies first so this layer is cached when only source changes.
COPY pyproject.toml uv.lock ./
RUN if [ "${INSTALL_DEV}" = "true" ]; then \
      uv pip install --system --no-cache -e ".[dev]"; \
    else \
      uv pip install --system --no-cache -e .; \
    fi

# Copy application source.
COPY . .

# Run as a non-root user for security.
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

# Cloud Run expects the container to listen on $PORT (default 8080).
ENV PORT=8080

EXPOSE 8080

# Run migrations then start the server.
# Migrations are run at container start so every replica is consistent.
CMD alembic upgrade head && \
    uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
