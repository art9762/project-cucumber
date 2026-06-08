# Analysis API — FastAPI over the shared Postgres (classification, scoring,
# research, embeddings/semantic search, auth). Runtime port 8113.
FROM python:3.13-slim

# Faster, quieter, no .pyc clutter; unbuffered logs for container stdout.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install the package from source. The build context is the analysis/ dir;
# .dockerignore keeps .env/.venv/caches out of the image.
COPY . .
RUN pip install .

# Drop privileges — never run uvicorn as root (see phase-6 hardening doc).
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8113

# Single image, scale via replicas. Host/port are container-internal; bind to
# all interfaces inside the container, expose only via the reverse proxy.
CMD ["uvicorn", "analysis.main:app", "--host", "0.0.0.0", "--port", "8113"]
