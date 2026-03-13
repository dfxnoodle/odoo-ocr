# ──────────────────────────────────────────────────────────────────────────────
# Stage 1: Build Vue / Vite frontend
# ──────────────────────────────────────────────────────────────────────────────
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts

COPY frontend/ ./
RUN npm run build
# Output lands in /app/backend/static (configured in vite.config.ts)


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2: Python runtime
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.14-slim AS runtime

# System deps: libgomp for PaddleOCR (optional), curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./

# Copy pre-built frontend static assets from stage 1
COPY --from=frontend-build /app/backend/static ./static

# Non-root user for least-privilege operation
RUN useradd -m -u 1001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
