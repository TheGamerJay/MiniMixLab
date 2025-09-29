# ---------- Frontend build ----------
FROM node:20-slim AS web
WORKDIR /app/frontend

# Install deps
COPY frontend/package*.json ./
# If you have package-lock.json, prefer ci; otherwise fallback to install
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi

# Build
COPY frontend/ ./
# Vite outDir is ../frontend_dist per our config; this will create /app/frontend_dist
RUN npm run build

# ---------- Backend runtime ----------
FROM python:3.11-slim

# System libs for librosa/soundfile + ffmpeg + rubberband (CPU)
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg rubberband-cli \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend and built frontend
COPY backend/ /app/backend/
COPY --from=web /app/frontend_dist /app/frontend_dist

# Python deps
RUN set -eux; for i in 1 2 3 4 5; do \
pip install --no-cache-dir --default-timeout=120 -r /app/backend/requirements.txt && break || (echo "pip attempt $i failed"; sleep 5); done

# Env
ENV HOST=0.0.0.0 \
    PORT=8080 \
    PYTHONUNBUFFERED=1 \
    ENABLE_SEPARATION=false

EXPOSE 8080

# Optional healthcheck (FastAPI root serves index.html if present)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:${PORT}/ || exit 1

# Run API (serves UI too)
CMD ["bash","-lc","cd /app/backend && uvicorn main:app --host ${HOST} --port ${PORT}"]

