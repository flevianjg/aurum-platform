FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps for asyncpg, argon2, pynacl, py_webauthn (cffi/cbor2)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependency layer (cached)
COPY pyproject.toml ./
RUN pip install --upgrade pip==24.3.1 \
    && pip install --no-cache-dir .

# Application code
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY tests ./tests

# Non-root user
RUN groupadd --system app && useradd --system --gid app --no-create-home app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# Default command is overridden by docker-compose; this is the production default
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*"]
