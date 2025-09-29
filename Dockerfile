# ---------- Frontend build ----------
FROM node:20-slim AS web
WORKDIR /app/web

# Install deps
COPY web/package*.json ./
RUN npm install --no-audit --no-fund

# Build
COPY web/ ./
RUN npm run build

# ---------- Backend runtime ----------
FROM python:3.11-slim

# System libs for FFmpeg and audio processing
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend and built frontend
COPY server/ /app/server/
COPY --from=web /app/web/dist /app/server/static

# Python deps
RUN pip install --no-cache-dir -r /app/server/requirements.txt

# Create storage directories
RUN mkdir -p /app/server/storage /app/server/mixes

# Env
ENV PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:${PORT}/healthz || exit 1

# Run Flask server
CMD ["python", "/app/server/app.py"]