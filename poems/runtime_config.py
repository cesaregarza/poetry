from django.core.exceptions import ImproperlyConfigured

REQUIRED_SPACES_ENV = (
    "AWS_STORAGE_BUCKET_NAME",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_S3_CUSTOM_DOMAIN",
    "AWS_S3_ENDPOINT_URL",
    "AWS_S3_REGION_NAME",
)


def validate_production_config(debug, database_url, environment):
    if debug:
        return
    if not database_url.startswith(("postgres://", "postgresql://")):
        raise ImproperlyConfigured(
            "DATABASE_URL must be an explicit PostgreSQL URL when DJANGO_DEBUG is false"
        )
    missing = [name for name in REQUIRED_SPACES_ENV if not environment.get(name)]
    if missing:
        raise ImproperlyConfigured(
            "Missing required production Spaces settings: " + ", ".join(missing)
        )
