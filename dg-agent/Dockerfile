# Multi-stage build: compile the React frontend, then run FastAPI serving API + static UI.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-ara poppler-utils fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* && useradd -m -u 10001 app
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/frontend/dist
RUN mkdir -p /data/storage && chown -R app /data
USER app
ENV FRONTEND_DIST=/app/frontend/dist STORAGE_DIR=/data/storage
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
