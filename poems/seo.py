import json
from urllib.parse import urlencode

from django.urls import reverse

from poems.social_cards import instagram_card_version, social_card_version


def absolute_site_url(request):
    return request.build_absolute_uri("/")


def canonical_url(request, page_number=None):
    url = request.build_absolute_uri(request.path)
    if page_number and page_number > 1:
        return f"{url}?{urlencode({'page': page_number})}"
    return url


def serialize_json_ld(payload):
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def site_social_card_url(request, site_settings):
    version = social_card_version(site_settings.site_title, site_settings.author_name)
    path = reverse("site_social_card", kwargs={"version": version})
    return request.build_absolute_uri(path)


def poem_social_card_url(request, poem, site_settings):
    version = social_card_version(poem.pk, poem.title, site_settings.author_name)
    path = reverse(
        "poem_social_card",
        kwargs={"page_id": poem.pk, "version": version},
    )
    return request.build_absolute_uri(path)


def poem_instagram_card_url(request, poem):
    version = instagram_card_version(
        poem.pk,
        poem.title,
        poem.poem_body,
        poem.dedication,
        request.get_host(),
    )
    path = reverse(
        "poem_instagram_card",
        kwargs={"page_id": poem.pk, "version": version},
    )
    return request.build_absolute_uri(path)
