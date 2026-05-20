FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        curl \
        tini \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash --uid 10001 app

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip \
 && pip install .

COPY app/ ./app/
COPY migrations/ ./migrations/

ENV FLASK_APP=app:create_app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail --silent http://localhost:8000/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]

CMD ["gunicorn", \
     "--workers", "2", \
     "--threads", "4", \
     "--worker-class", "gthread", \
     "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:create_app()"]
