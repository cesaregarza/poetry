import json
from urllib.parse import urlencode


def absolute_site_url(request):
    return request.build_absolute_uri("/")


def canonical_url(request, page_number=None):
    url = request.build_absolute_uri(request.path)
    if page_number and page_number > 1:
        return f"{url}?{urlencode({'page': page_number})}"
    return url


def serialize_json_ld(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
