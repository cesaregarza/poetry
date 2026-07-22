from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured


def validate_cloudflare_access_config(team_domain, audience, allowed_email, required=False):
    """Reject partial or ambiguous Access configuration during startup."""
    if not team_domain and not audience:
        if required:
            raise ImproperlyConfigured(
                "Cloudflare Access validation is required but issuer and audience are absent"
            )
        return
    if not team_domain or not audience:
        raise ImproperlyConfigured(
            "CLOUDFLARE_ACCESS_TEAM_DOMAIN and CLOUDFLARE_ACCESS_AUD must be set together"
        )

    parsed = urlsplit(team_domain)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ImproperlyConfigured(
            "CLOUDFLARE_ACCESS_TEAM_DOMAIN must be an origin-only HTTPS URL "
            "without a trailing slash"
        )
    if audience.strip() != audience or not audience:
        raise ImproperlyConfigured("CLOUDFLARE_ACCESS_AUD must be a non-empty exact audience")
    if allowed_email != "cesar@cegarza.com":
        raise ImproperlyConfigured(
            "CLOUDFLARE_ACCESS_ALLOWED_EMAIL must be exactly cesar@cegarza.com"
        )
