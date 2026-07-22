FROM python:3.12-alpine AS builder

RUN apk add --no-cache \
    build-base \
    linux-headers \
    libffi-dev \
    openssl-dev

WORKDIR /build

COPY pyproject.toml ./
COPY app ./app

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install .

FROM python:3.12-alpine AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apk add --no-cache \
    ca-certificates \
    tzdata \
    && addgroup -g 10001 appgroup \
    && adduser \
        -D \
        -H \
        -u 10001 \
        -G appgroup \
        -s /sbin/nologin \
        appuser

WORKDIR /srv/app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=10001:10001 app ./app

RUN mkdir -p /srv/app/data && chown 10001:10001 /srv/app/data

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
