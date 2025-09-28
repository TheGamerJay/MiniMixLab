FROM node:20-slim AS web
WORKDIR /app/frontend
COPY frontend/ ./
RUN npm ci --no-audit --no-fund && npm run build

FROM python:3.11-slim
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg rubberband-cli \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/ /app/backend/
COPY --from=web /app/frontend_dist /app/frontend_dist
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
ENV PORT=8080 HOST=0.0.0.0
EXPOSE 8080
CMD ["bash","-lc","cd /app/backend && uvicorn main:app --host ${HOST} --port ${PORT}"]