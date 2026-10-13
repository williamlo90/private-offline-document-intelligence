# syntax=docker/dockerfile:1.7
# Phase 7 lab image. Runtime installs no packages and uses only local adapters.
FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-ind && \
    rm -rf /var/lib/apt/lists/*
COPY --from=wheels . /tmp/wheels
COPY requirements.lock .
RUN pip install --no-index --find-links=/tmp/wheels --no-cache-dir -r requirements.lock && \
    rm -rf /tmp/wheels
COPY backend backend
COPY config config
COPY evaluation/development evaluation/development
COPY frontend/dist frontend/dist
RUN useradd --uid 10001 --create-home app
USER app
CMD ["python","-m","uvicorn","backend.main:load_app","--factory","--host","0.0.0.0","--port","8077","--no-access-log"]
