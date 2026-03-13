# ═══════════════════════════════════════════════════════════
# APIS v5.0 — Backend Dockerfile (Production)
# Multi-stage build: slim Python 3.11 + OpenCV deps
# ═══════════════════════════════════════════════════════════

FROM python:3.11-slim AS base

# System deps for OpenCV, GDAL, PostGIS
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m apis && chown -R apis:apis /app
USER apis

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
