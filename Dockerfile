# HuggingFace Spaces Docker deployment.
# Builds the React frontend, then serves it as static files from the same
# FastAPI process that serves the API. Single origin means no CORS setup.

# ---- Stage 1: build the frontend ----
FROM node:20-slim AS frontend-build

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
ENV VITE_API_URL=""
RUN npm run build


# ---- Stage 2: the app ----
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-build /build/dist ./static

ENV PORT=7860
EXPOSE 7860

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
