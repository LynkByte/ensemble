# ── Build stage ────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir --prefix=/install .

# ── Runtime stage ─────────────────────────────────────────────────
FROM python:3.11-slim

LABEL maintainer="Sanjaya De Silva <sanjaya@example.com>"
LABEL org.opencontainers.image.title="ensemble-mcp"
LABEL org.opencontainers.image.description="MCP server for vector memory, token tracking, drift detection, model routing, skills discovery, session management, and codebase indexing."
LABEL org.opencontainers.image.version="0.1.0"
LABEL org.opencontainers.image.source="https://github.com/LynkByte/ensemble"
LABEL org.opencontainers.image.licenses="MIT"

# Create non-root user
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --create-home app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Ensure cache directories exist with correct ownership
RUN mkdir -p /home/app/.cache/ensemble-mcp/models && \
    chown -R app:app /home/app/.cache

USER app
WORKDIR /home/app

# Pre-download the ONNX model during build (optional — speeds up first run)
# Uncomment the next two lines to bake the model into the image:
# RUN python -c "from ensemble_mcp.memory.embeddings import EmbeddingModel; EmbeddingModel()._ensure_model()"

ENTRYPOINT ["ensemble-mcp"]
CMD ["serve"]
