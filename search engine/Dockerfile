# Collector — FastAPI + in-process APScheduler that polls public sources
# (GitHub/Reddit/HN/arXiv) into Postgres. Runtime port 8114.
#
# IMPORTANT: the scheduler lives inside the process (find_engine/main.py
# lifespan), so this image must run as EXACTLY ONE worker — never scale it with
# uvicorn --workers > 1 or multiple replicas, or sources get polled N times.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY . .
RUN pip install .

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8114

# Exactly one worker — see note above.
CMD ["uvicorn", "find_engine.main:app", "--host", "0.0.0.0", "--port", "8114", "--workers", "1"]
