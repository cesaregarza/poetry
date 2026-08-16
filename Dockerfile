FROM python:3.12.13-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv==0.8.17

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY manage.py ./
COPY poetry_site ./poetry_site
COPY poems ./poems
COPY templates ./templates
COPY static ./static
COPY third_party ./third_party

RUN DJANGO_DEBUG=false \
    DJANGO_SECRET_KEY=build-only-not-for-runtime \
    DATABASE_URL=postgresql://build-only:build-only@build-only.invalid/build-only \
    AWS_STORAGE_BUCKET_NAME=build-only \
    AWS_ACCESS_KEY_ID=build-only \
    AWS_SECRET_ACCESS_KEY=build-only \
    AWS_S3_CUSTOM_DOMAIN=build-only.invalid \
    AWS_S3_ENDPOINT_URL=https://build-only.invalid \
    AWS_S3_REGION_NAME=nyc3 \
    CLOUDFLARE_ACCESS_REQUIRED=false \
    .venv/bin/python manage.py collectstatic --noinput --clear


FROM python:3.12.13-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    TMPDIR=/tmp

WORKDIR /app

RUN groupadd --gid 10001 poetry \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /app poetry

COPY --from=builder --chown=10001:10001 /app /app

USER 10001:10001
EXPOSE 8000

CMD ["gunicorn", "poetry_site.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "60", "--worker-tmp-dir", "/tmp", "--access-logfile", "-", "--error-logfile", "-"]
