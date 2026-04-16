# Stage 1: Build React frontend
FROM node:20-slim AS frontend
WORKDIR /app/testmcpy/ui
COPY testmcpy/ui/package*.json ./
RUN npm ci --no-audit --no-fund
COPY testmcpy/ui/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
COPY testmcpy/ testmcpy/
RUN pip install --no-cache-dir ".[server]"

# Copy built frontend from stage 1
COPY --from=frontend /app/testmcpy/ui/dist testmcpy/ui/dist

# Create data directory for persistent storage
RUN mkdir -p /app/.testmcpy

# Default environment variables
ENV TESTMCPY_DB_PATH=/app/.testmcpy/storage.db

# Volume for persistent data (database, configs)
VOLUME /app/.testmcpy

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["testmcpy", "serve", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
