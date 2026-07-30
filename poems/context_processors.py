from poems.models import PoetrySiteSettings, public_collections
from poems.seo import absolute_site_url, canonical_url, serialize_json_ld


def public_navigation(request):
    site_settings = PoetrySiteSettings.for_request(request)
    site_url = absolute_site_url(request)
    author_url = request.build_absolute_uri("/about/")
    same_as = [
        url
        for url in (
            site_settings.website_url,
            site_settings.mastodon_url,
            site_settings.instagram_url,
        )
        if url
    ]

    author = {
        "@type": "Person",
        "@id": f"{site_url}#author",
        "name": site_settings.author_name,
        "url": author_url,
    }
    if same_as:
        author["sameAs"] = same_as

    structured_data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{site_url}#website",
                "url": site_url,
                "name": site_settings.site_title,
                "description": f"Poetry by {site_settings.author_name}.",
                "inLanguage": "en-US",
                "publisher": {"@id": f"{site_url}#author"},
            },
            author,
        ],
    }

    return {
        "canonical_url": canonical_url(request),
        "public_collections": public_collections(),
        "seo_noindex": False,
        "seo_site_url": site_url,
        "site_structured_data": serialize_json_ld(structured_data),
    }
