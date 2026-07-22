# Cesar Garza — Poetry

A small, server-rendered poetry publication built with Django and Wagtail. The
public site is intentionally quiet: exact poem text, generous whitespace, fast
pages, and a system-first light/dark theme. Wagtail provides the private editing
workflow at `/admin/`.

## Local development

Requirements: Docker with Compose, or Python 3.12 and `uv` 0.8.17.

```bash
cp .env.example .env
docker compose up --build
```

The app is then available at <http://localhost:8000>. The Compose startup is
idempotent: it applies migrations and creates the initial Home, Poems, and About
pages. Create an administrator interactively:

```bash
docker compose exec web python manage.py createsuperuser
```

For a native process, start PostgreSQL and run:

```bash
uv sync --frozen
uv run python manage.py migrate
uv run python manage.py bootstrap_site --hostname localhost --port 8000
uv run python manage.py runserver
```

## Verification

The pull-request workflow runs the same commands shown below against PostgreSQL
16. Browser tests require Playwright's Chromium bundle.

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest -m "not browser"
uv run python manage.py collectstatic --noinput --clear
uv run playwright install --with-deps chromium
DJANGO_ALLOW_ASYNC_UNSAFE=true uv run pytest -m browser --browser chromium
docker build -t poetry:verify .
```

The website makes no third-party font requests. Source Serif 4 and Inter are
vendored as WOFF2 assets; their provenance and upstream licenses are recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This repository intentionally
has no project-level open-source license.

## Production contract

The image runs as UID/GID `10001`, listens on port `8000`, writes temporary
files only below `/tmp`, and stores media in a DigitalOcean Space. Kubernetes
mounts an `emptyDir` at `/tmp`; the root filesystem may remain read-only.

Required secrets:

- `DJANGO_SECRET_KEY`
- `DATABASE_URL`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

Deployment configuration:

- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=poetry.cegarza.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://poetry.cegarza.com`
- `WAGTAILADMIN_BASE_URL=https://poetry.cegarza.com`
- `SITE_HOSTNAME=poetry.cegarza.com`
- `DATABASE_SSL_REQUIRE=true`
- `AWS_STORAGE_BUCKET_NAME=cegarza-poetry-media`
- `AWS_S3_REGION_NAME=nyc3`
- `AWS_S3_ENDPOINT_URL=https://nyc3.digitaloceanspaces.com`
- `AWS_S3_CUSTOM_DOMAIN=cegarza-poetry-media.nyc3.cdn.digitaloceanspaces.com`
- `CLOUDFLARE_ACCESS_TEAM_DOMAIN=https://<team>.cloudflareaccess.com`
- `CLOUDFLARE_ACCESS_AUD=<application audience>`
- `CLOUDFLARE_ACCESS_ALLOWED_EMAIL=cesar@cegarza.com`
- `CLOUDFLARE_ACCESS_REQUIRED=true`

`CLOUDFLARE_ACCESS_TEAM_DOMAIN` and `CLOUDFLARE_ACCESS_AUD` are an all-or-nothing
pair. When configured, every exact `/admin` or `/admin/…` request must present a
valid RS256 `Cf-Access-Jwt-Assertion` from that issuer and audience for the exact
allowed email. Missing or invalid assertions receive `403` before Wagtail; a
valid assertion continues to the normal Wagtail login. The gate is disabled only
when both values are absent, which supports local development and isolated tests.
Production defaults `CLOUDFLARE_ACCESS_REQUIRED` to true; an ingress-free staging
rollout may set it false explicitly, but the public launch must restore true.

Before each rollout, run:

```bash
python manage.py migrate --noinput
python manage.py bootstrap_site --hostname poetry.cegarza.com
```

Liveness is exposed at `/healthz` without a database query. Readiness is
database-backed at `/readyz`.

Recovery and rollback procedures are in [docs/operations.md](docs/operations.md).
