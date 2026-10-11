# =============================================================================
# Client Connector Service - Dockerfile
# Port: 8095
# Role: Gateway for AI agents to connect to ConFuse infrastructure
# =============================================================================

# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies for building packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into a virtual environment for easy copying
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    dumb-init \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user before changing ownership
RUN useradd -m appuser

# Copy source code with strict ownership
COPY --chown=appuser:appuser app ./app

# Set explicit ownership of working directory
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# PORT is supplied at runtime via .map.env / .secret.env (see .cline/rules/env-policy.md)
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8095

# Health check optimized for Render
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Use dumb-init as PID 1 for proper signal handling
ENTRYPOINT ["dumb-init", "--"]

# Run
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"
