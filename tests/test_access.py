import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, override_settings

from poems.access_config import validate_cloudflare_access_config
from poems.middleware import CloudflareJWKCache

TEAM_DOMAIN = "https://poetry.cloudflareaccess.com"
AUDIENCE = "0123456789abcdef0123456789abcdef"
ALLOWED_EMAIL = "cesar@cegarza.com"


@pytest.fixture(scope="module")
def signing_keys():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key(), other_private_key


def make_assertion(private_key, *, kid="test-key", algorithm="RS256", **overrides):
    now = int(time.time())
    claims = {
        "iss": TEAM_DOMAIN,
        "aud": AUDIENCE,
        "email": ALLOWED_EMAIL,
        "iat": now - 5,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm=algorithm, headers={"kid": kid})


def configured_access():
    return override_settings(
        CLOUDFLARE_ACCESS_TEAM_DOMAIN=TEAM_DOMAIN,
        CLOUDFLARE_ACCESS_AUD=AUDIENCE,
        CLOUDFLARE_ACCESS_ALLOWED_EMAIL=ALLOWED_EMAIL,
        CLOUDFLARE_ACCESS_REQUIRED=True,
    )


def test_access_config_must_be_complete_and_exact():
    validate_cloudflare_access_config("", "", ALLOWED_EMAIL)

    with pytest.raises(ImproperlyConfigured):
        validate_cloudflare_access_config("", "", ALLOWED_EMAIL, required=True)
    with pytest.raises(ImproperlyConfigured):
        validate_cloudflare_access_config(TEAM_DOMAIN, "", ALLOWED_EMAIL)
    with pytest.raises(ImproperlyConfigured):
        validate_cloudflare_access_config(
            "http://poetry.cloudflareaccess.com", AUDIENCE, ALLOWED_EMAIL
        )
    with pytest.raises(ImproperlyConfigured):
        validate_cloudflare_access_config(f"{TEAM_DOMAIN}/", AUDIENCE, ALLOWED_EMAIL)
    with pytest.raises(ImproperlyConfigured):
        validate_cloudflare_access_config(TEAM_DOMAIN, AUDIENCE, "another@example.com")


@pytest.mark.django_db
def test_access_gate_disabled_preserves_normal_wagtail_login(site_tree):
    response = Client().get("/admin/")
    assert response.status_code == 302
    assert response["Location"].startswith("/admin/login/")


@pytest.mark.django_db
def test_access_gate_rejects_missing_assertion(site_tree):
    with configured_access(), patch("poems.middleware.get_shared_jwk_cache") as jwks:
        response = Client().get("/admin/")

    assert response.status_code == 403
    assert response.content == b"Forbidden\n"
    jwks.return_value.get_signing_key.assert_not_called()


@pytest.mark.django_db
def test_access_gate_accepts_valid_signature_claims_and_email(site_tree, signing_keys):
    private_key, public_key, _ = signing_keys
    assertion = make_assertion(private_key)

    with configured_access(), patch("poems.middleware.get_shared_jwk_cache") as jwks:
        jwks.return_value.get_signing_key.return_value = public_key
        response = Client().get(
            "/admin/",
            HTTP_CF_ACCESS_JWT_ASSERTION=assertion,
        )

    assert response.status_code == 302
    assert response["Location"].startswith("/admin/login/")
    jwks.assert_called_once_with(f"{TEAM_DOMAIN}/cdn-cgi/access/certs")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("claim_overrides", "use_wrong_key"),
    [
        ({}, True),
        ({"aud": "wrong-audience"}, False),
        ({"iss": "https://attacker.example"}, False),
        ({"email": "attacker@example.com"}, False),
        ({"exp": 0}, False),
    ],
)
def test_access_gate_rejects_bad_signature_or_claims(
    site_tree,
    signing_keys,
    claim_overrides,
    use_wrong_key,
):
    private_key, public_key, other_private_key = signing_keys
    assertion = make_assertion(
        other_private_key if use_wrong_key else private_key, **claim_overrides
    )

    with configured_access(), patch("poems.middleware.get_shared_jwk_cache") as jwks:
        jwks.return_value.get_signing_key.return_value = public_key
        response = Client().get(
            "/admin/",
            HTTP_CF_ACCESS_JWT_ASSERTION=assertion,
        )

    assert response.status_code == 403


@pytest.mark.django_db
def test_access_gate_never_intercepts_public_routes(site_tree):
    with configured_access(), patch("poems.middleware.get_shared_jwk_cache") as jwks:
        response = Client().get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    jwks.return_value.get_signing_key.assert_not_called()


def test_jwk_cache_reuses_valid_key_without_refetching(signing_keys):
    private_key, public_key, _ = signing_keys
    clock = [100.0]
    cache = CloudflareJWKCache(
        f"{TEAM_DOMAIN}/cdn-cgi/access/certs",
        clock=lambda: clock[0],
    )
    assertion = make_assertion(private_key)

    with patch.object(cache, "_download_keys", return_value={"test-key": public_key}) as fetch:
        assert cache.get_signing_key(assertion) is public_key
        assert cache.get_signing_key(assertion) is public_key

    assert fetch.call_count == 1


def test_many_unknown_kids_trigger_at_most_one_bounded_refresh(signing_keys):
    private_key, public_key, _ = signing_keys
    clock = [100.0]
    cache = CloudflareJWKCache(
        f"{TEAM_DOMAIN}/cdn-cgi/access/certs",
        min_refresh_interval=60,
        clock=lambda: clock[0],
    )

    with patch.object(cache, "_download_keys", return_value={"known-key": public_key}) as fetch:
        for number in range(25):
            assertion = make_assertion(private_key, kid=f"unknown-{number}")
            with pytest.raises(jwt.InvalidTokenError):
                cache.get_signing_key(assertion)
        assert fetch.call_count == 1

        clock[0] += 61
        with pytest.raises(jwt.InvalidTokenError):
            cache.get_signing_key(make_assertion(private_key, kid="another-unknown"))
        assert fetch.call_count == 2


def test_jwk_cache_rejects_malformed_key_document():
    cache = CloudflareJWKCache(f"{TEAM_DOMAIN}/cdn-cgi/access/certs")
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"keys": "not-a-list"}'

    with (
        patch("poems.middleware.urlopen", return_value=response),
        pytest.raises(jwt.PyJWKClientError),
    ):
        cache._download_keys()


def test_jwk_cache_rejects_non_rs256_or_missing_kid_without_fetch(signing_keys):
    private_key, _, _ = signing_keys
    cache = CloudflareJWKCache(f"{TEAM_DOMAIN}/cdn-cgi/access/certs")

    hs_assertion = make_assertion("test-secret", algorithm="HS256")
    with patch.object(cache, "_download_keys") as fetch:
        with pytest.raises(jwt.InvalidAlgorithmError):
            cache.get_signing_key(hs_assertion)
        fetch.assert_not_called()

    now = int(time.time())
    no_kid_assertion = jwt.encode(
        {
            "iss": TEAM_DOMAIN,
            "aud": AUDIENCE,
            "email": ALLOWED_EMAIL,
            "iat": now - 5,
            "exp": now + 300,
        },
        private_key,
        algorithm="RS256",
    )
    with patch.object(cache, "_download_keys") as fetch:
        with pytest.raises(jwt.InvalidTokenError):
            cache.get_signing_key(no_kid_assertion)
        fetch.assert_not_called()
