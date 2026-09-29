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

For the full local CI sequence, point `DATABASE_URL` at a disposable loopback
PostgreSQL database and run `./scripts/ci_preflight.py --image-tag poetry:ci-local`.
It requires uv, Docker, and the installed Playwright Chromium browser. The production
image also checks that Pillow's RAQM text layout is available, so card wrapping
matches local previews.

## Instagram exports

In the Wagtail poem editor, **Social previews** generates images from the latest
saved revision. Short poems retain the single 1080 × 1350 PNG. Longer poems
automatically become numbered portrait slides using the same typography and site
signature. Stanzas stay together when they fit; oversized stanzas continue onto
the next slide without dropping text. The layout favors fewer slides at a
comfortable text size (32–46 px), then chooses the largest type that fits that
slide count. It uses consistent sizing and tighter leading across the carousel,
with a maximum of 20 slides. Smaller type is reserved for poems that would
otherwise exceed that limit. Content that still cannot fit shows an actionable
export error.

Wrapped continuations use a hanging indent on the poem page and Instagram cards,
so they remain distinct from authored line breaks. Blank lines still separate stanzas.

Use **Download carousel ZIP** for the full set, or download individual slides.
Extract the ZIP and select its numbered PNGs in order when creating an Instagram
post. Save edits before downloading again. Carousel previews and ZIP downloads
require permission to edit the poem, are never publicly cached, and do not
publish the draft or post to Instagram.

To inspect the renderer using a saved public poem page without a database:

```bash
uv run scripts/preview_instagram_carousel.py --html /tmp/poem.html \
  --output-dir /tmp/poem-preview --footer poetry.cegarza.com --screenshot
```

The output directory must be new. This creates numbered PNGs, a ZIP, an HTML
preview, and (with Chromium installed) a JPEG contact sheet. The command reports
the slide count and text size as JSON and verifies all poem characters remain in
order. It does not fetch pages or publish changes.

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
