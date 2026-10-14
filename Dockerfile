# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm AS backend
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY Verifai-backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 10001 verifai
COPY --chown=verifai:verifai Verifai-backend/app ./app
COPY --chown=verifai:verifai Verifai-backend/migrations ./migrations
COPY --chown=verifai:verifai docker/start_backend.py ./start_backend.py
RUN mkdir -p /app/logs && chown verifai:verifai /app/logs
USER verifai
EXPOSE 8000
CMD ["python", "start_backend.py"]

# Optional CPU inference image; selected by compose.local-model.yaml.
FROM backend AS backend-local
USER root
RUN pip install --no-cache-dir torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir transformers==5.15.0 sentencepiece
USER verifai

FROM node:24-bookworm-slim AS extension-build
WORKDIR /extension
COPY verifai-extension/package.json verifai-extension/package-lock.json ./
RUN npm ci
COPY verifai-extension/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS extension-package
COPY --from=extension-build /extension/dist /extension/dist
COPY verifai-extension/package.py /extension/package.py
RUN python /extension/package.py --output /artifacts/verifai-extension.zip

FROM node:24-bookworm-slim AS frontend-build
WORKDIR /frontend
COPY verifai-frontend/package.json verifai-frontend/package-lock.json ./
RUN npm ci
COPY verifai-frontend/ ./
COPY --from=extension-package /artifacts/verifai-extension.zip ./public/downloads/verifai-extension.zip
ENV VITE_API_URL=/api/v1 VITE_LANDING_ONLY=false VITE_BASE_PATH=/
RUN npm run build

FROM nginx:stable-alpine AS frontend
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /frontend/dist /usr/share/nginx/html
EXPOSE 80
