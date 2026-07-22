# Operations and recovery

## Deployment and rollback

The GitOps repository pins `image.tag` to `sha-<source commit>`. A release is
ready only after the PreSync job succeeds with:

```bash
python manage.py migrate --noinput
python manage.py bootstrap_site --hostname poetry.cegarza.com
```

To roll back application code, restore the previous immutable `sha-*` tag in
`helm/poetry/values.yaml` and merge that GitOps change. Do not reverse a database
migration blindly. Confirm migration compatibility first; if a schema rollback
is genuinely required, restore a database backup into an isolated database,
verify it, then arrange a maintenance window.

## Database backup and restore

DigitalOcean managed PostgreSQL backups remain the primary disaster-recovery
mechanism. Before a migration with meaningful data risk, also create a logical
export from a trusted workstation or one-shot Kubernetes job:

```bash
pg_dump --format=custom --no-owner --no-acl "$DATABASE_URL" --file=poetry.dump
pg_restore --list poetry.dump
```

Never commit a dump. Encrypt it at rest, record the source cluster and timestamp,
and test restore into a separate database using `pg_restore --clean --if-exists`.
After restore, run `python manage.py check`, compare page and image counts, and
open representative drafts and published pages before changing production.

## Media recovery

All uploads live in the `cegarza-poetry-media` Space; there is no media PVC.
Keep object versioning enabled. Recover a deleted or overwritten object by
promoting the intended prior version in the Spaces/S3 API, then verify both the
original URL and a Wagtail rendition. Database and Space recovery points should
be close in time because Wagtail image rows refer to object keys.

## Health and incident checks

- `/healthz` proves the process can serve HTTP without depending on PostgreSQL.
- `/readyz` executes `SELECT 1`; a failure removes the pod from Service endpoints.
- A healthy rollout has one ready pod, a successful migration/bootstrap job, and
  an Argo CD application that is both `Synced` and `Healthy` at the expected Git
  revision.
- Validate public pages anonymously and confirm `/admin/` is challenged by
  Cloudflare Access before Wagtail login is reachable.
- Confirm `cegarza.com` still resolves to and serves Ghost after every DNS change.

## Credential rotation

Rotate PostgreSQL, Spaces, Django, and registry credentials independently. Write
only SOPS/age ciphertext to GarzAICluster, reconcile secrets before restarting
the Deployment, and retain the previous encrypted Git revision long enough for a
bounded rollback. A Django secret-key rotation invalidates sessions by design.

