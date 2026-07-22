import json
import threading
import time
from secrets import compare_digest
from urllib.error import URLError
from urllib.request import Request, urlopen

import jwt
from django.conf import settings
from django.http import HttpResponseForbidden


class CloudflareJWKCache:
    """Bound outbound JWK refreshes while honoring normal Access key rotation."""

    max_response_bytes = 1024 * 1024

    def __init__(
        self,
        certs_url,
        *,
        timeout=5,
        ttl=300,
        min_refresh_interval=60,
        clock=time.monotonic,
    ):
        self.certs_url = certs_url
        self.timeout = timeout
        self.ttl = ttl
        self.min_refresh_interval = min_refresh_interval
        self.clock = clock
        self._keys = {}
        self._expires_at = 0.0
        self._last_refresh_attempt = float("-inf")
        self._lock = threading.Lock()

    def get_signing_key(self, assertion):
        header = jwt.get_unverified_header(assertion)
        if header.get("alg") != "RS256":
            raise jwt.InvalidAlgorithmError("Cloudflare Access assertion must use RS256")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise jwt.InvalidTokenError("Cloudflare Access assertion has no key id")

        with self._lock:
            now = self.clock()
            key = self._keys.get(kid)
            if key is not None and now < self._expires_at:
                return key
            if now - self._last_refresh_attempt < self.min_refresh_interval:
                raise jwt.InvalidTokenError("Cloudflare Access key id is not cached")

            self._last_refresh_attempt = now
            self._keys = self._download_keys()
            self._expires_at = self.clock() + self.ttl
            key = self._keys.get(kid)
            if key is None:
                raise jwt.InvalidTokenError("Cloudflare Access key id is unknown")
            return key

    def _download_keys(self):
        request = Request(
            self.certs_url,
            headers={
                "Accept": "application/json",
                "User-Agent": "poetry.cegarza.com-access-validator/1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(self.max_response_bytes + 1)
            if len(raw) > self.max_response_bytes:
                raise jwt.PyJWKClientError("Cloudflare Access JWK response is too large")
            payload = json.loads(raw)
            key_data = payload.get("keys") if isinstance(payload, dict) else None
            if not isinstance(key_data, list):
                raise jwt.PyJWKClientError("Cloudflare Access JWK response has no keys")

            keys = {}
            for item in key_data:
                if not isinstance(item, dict):
                    continue
                kid = item.get("kid")
                if (
                    not isinstance(kid, str)
                    or not kid
                    or item.get("kty") != "RSA"
                    or item.get("alg") not in {None, "RS256"}
                ):
                    continue
                keys[kid] = jwt.PyJWK.from_dict(item, algorithm="RS256").key
            if not keys:
                raise jwt.PyJWKClientError("Cloudflare Access JWK response has no RS256 keys")
            return keys
        except (URLError, OSError, json.JSONDecodeError) as error:
            raise jwt.PyJWKClientError("Unable to refresh Cloudflare Access keys") from error


_shared_jwk_caches = {}
_shared_jwk_caches_lock = threading.Lock()


def get_shared_jwk_cache(certs_url):
    with _shared_jwk_caches_lock:
        cache = _shared_jwk_caches.get(certs_url)
        if cache is None:
            cache = CloudflareJWKCache(certs_url)
            _shared_jwk_caches[certs_url] = cache
        return cache


class CloudflareAccessAdminMiddleware:
    """Verify Cloudflare Access JWTs before any Wagtail admin response."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.team_domain = settings.CLOUDFLARE_ACCESS_TEAM_DOMAIN
        self.audience = settings.CLOUDFLARE_ACCESS_AUD
        self.allowed_email = settings.CLOUDFLARE_ACCESS_ALLOWED_EMAIL
        self.enabled = bool(self.team_domain and self.audience)
        self.jwks = None
        if self.enabled:
            self.jwks = get_shared_jwk_cache(f"{self.team_domain}/cdn-cgi/access/certs")

    def __call__(self, request):
        if not self._is_admin_path(request.path_info) or not self.enabled:
            return self.get_response(request)

        assertion = request.META.get("HTTP_CF_ACCESS_JWT_ASSERTION", "")
        if not assertion:
            return self._forbidden()

        try:
            signing_key = self.jwks.get_signing_key(assertion)
            claims = jwt.decode(
                assertion,
                signing_key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.team_domain,
                options={"require": ["exp", "iat", "iss", "aud", "email"]},
            )
            email = claims.get("email")
            if not isinstance(email, str) or not compare_digest(email, self.allowed_email):
                return self._forbidden()
        except (jwt.PyJWTError, TypeError, ValueError):
            return self._forbidden()

        return self.get_response(request)

    @staticmethod
    def _is_admin_path(path):
        return path == "/admin" or path.startswith("/admin/")

    @staticmethod
    def _forbidden():
        return HttpResponseForbidden("Forbidden\n", content_type="text/plain; charset=utf-8")
