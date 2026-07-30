import json
import re
from io import BytesIO
from urllib.parse import urlparse

import pytest
from PIL import Image

from poems.models import Collection, PoemPage
from poems.social_cards import (
    INSTAGRAM_BODY_MAX_SIZE,
    InstagramCardTooLong,
    instagram_card_layout,
    instagram_card_version,
)

pytestmark = pytest.mark.django_db


def structured_data(html, schema):
    match = re.search(
        rf'<script type="application/ld\+json" data-schema="{schema}">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert match
    return json.loads(match.group(1))


def meta_content(html, property_name):
    match = re.search(
        rf'<meta (?:property|name)="{re.escape(property_name)}" content="([^"]+)">',
        html,
    )
    assert match
    return match.group(1)


def test_core_pages_have_descriptive_metadata_and_canonical_urls(client, site_tree):
    expected = {
        "/": (
            "Poetry by Cesar Garza — Love, Family, and Daily Life",
            "Short poems by Cesar Garza about love, family, work, and the meaning "
            "inside ordinary days.",
        ),
        "/poems/": (
            "Poems by Cesar Garza — Poetry Archive",
            "Browse short poems by Cesar Garza about love, family, work, and ordinary life.",
        ),
        "/about/": (
            "About Cesar Garza — Poet and Software Engineer",
            "Cesar Garza is a Texas poet and software engineer writing short poems about "
            "love, family, work, and ordinary days.",
        ),
    }

    for path, (title, description) in expected.items():
        html = client.get(path).content.decode()
        assert f"<title>{title}</title>" in html
        assert f'<meta name="description" content="{description}">' in html
        assert f'<link rel="canonical" href="http://testserver{path}">' in html
        assert f'<meta property="og:url" content="http://testserver{path}">' in html
        assert '<meta name="twitter:card" content="summary_large_image">' in html
        assert re.search(
            r'<meta property="og:image" '
            r'content="http://testserver/og/site/[0-9a-f]{12}\.png">',
            html,
        )
        assert '<meta name="robots" content="noindex, follow">' not in html


def test_poem_metadata_and_structured_data_are_specific(client, live_poem):
    html = client.get("/poems/small-hours/").content.decode()

    assert "<title>Small Hours — A Poem by Cesar Garza</title>" in html
    assert '<meta name="description" content="A poem about the attentive night.">' in html
    assert '<meta property="og:type" content="article">' in html
    assert '<meta property="og:title" content="Small Hours — A Poem by Cesar Garza">' in html
    assert '<link rel="canonical" href="http://testserver/poems/small-hours/">' in html
    assert '<meta property="article:author" content="http://testserver/about/">' in html
    social_image_url = meta_content(html, "og:image")
    assert re.fullmatch(
        rf"http://testserver/og/poems/{live_poem.pk}/[0-9a-f]{{12}}\.png",
        social_image_url,
    )
    assert meta_content(html, "twitter:image") == social_image_url
    assert '<meta property="og:image:type" content="image/png">' in html
    assert '<meta property="og:image:width" content="1200">' in html
    assert '<meta property="og:image:height" content="630">' in html

    site_schema = structured_data(html, "site")
    website, author = site_schema["@graph"]
    assert website == {
        "@type": "WebSite",
        "@id": "http://testserver/#website",
        "url": "http://testserver/",
        "name": "Cesar Garza — Poetry",
        "description": "Poetry by Cesar Garza.",
        "inLanguage": "en-US",
        "publisher": {"@id": "http://testserver/#author"},
    }
    assert author == {
        "@type": "Person",
        "@id": "http://testserver/#author",
        "name": "Cesar Garza",
        "url": "http://testserver/about/",
    }

    poem_schema = structured_data(html, "poem")
    assert poem_schema["@type"] == "CreativeWork"
    assert poem_schema["@id"] == "http://testserver/poems/small-hours/#poem"
    assert poem_schema["name"] == "Small Hours"
    assert poem_schema["description"] == "A poem about the attentive night."
    assert poem_schema["genre"] == "Poetry"
    assert poem_schema["image"] == social_image_url
    assert poem_schema["author"] == {"@id": "http://testserver/#author"}
    assert poem_schema["datePublished"] == "2026-07-21"
    assert poem_schema["keywords"] == ["night"]


def test_poem_without_editorial_description_gets_a_unique_fallback(client, site_tree):
    poem = PoemPage(
        title="Unwritten Weather",
        slug="unwritten-weather",
        poem_body="The forecast forgets us.",
        live=False,
    )
    site_tree["poem_index"].add_child(instance=poem)
    poem.save_revision().publish()

    html = client.get("/poems/unwritten-weather/").content.decode()
    description = "Read “Unwritten Weather,” a poem by Cesar Garza."
    assert f'<meta name="description" content="{description}">' in html
    assert structured_data(html, "poem")["description"] == description


def test_search_and_filtered_archive_pages_are_not_indexed(client, site_tree):
    search_html = client.get("/search/", {"q": "moon"}).content.decode()
    filtered_html = client.get("/poems/", {"q": "moon"}).content.decode()
    archive_html = client.get("/poems/").content.decode()
    empty_collections_html = client.get("/collections/").content.decode()

    assert '<meta name="robots" content="noindex, follow">' in search_html
    assert '<link rel="canonical" href="http://testserver/search/">' in search_html
    assert '<meta name="robots" content="noindex, follow">' in filtered_html
    assert '<link rel="canonical" href="http://testserver/poems/">' in filtered_html
    assert '<meta name="robots" content="noindex, follow">' not in archive_html
    assert '<meta name="robots" content="noindex, follow">' in empty_collections_html


def test_sitemap_includes_only_public_collection_and_theme_hubs(client, site_tree, live_poem):
    public_collection = Collection.objects.create(name="Field Notes")
    empty_collection = Collection.objects.create(name="Empty Collection")
    live_poem.collection = public_collection
    live_poem.save_revision().publish()

    draft = PoemPage(
        title="Hidden Theme",
        slug="hidden-theme",
        poem_body="not yet",
        live=False,
    )
    site_tree["poem_index"].add_child(instance=draft)
    draft.themes.add("secret")
    draft.save_revision()

    xml = client.get("/sitemap.xml").content.decode()
    collection_index_html = client.get("/collections/").content.decode()
    assert "http://testserver/collections/" in xml
    assert "http://testserver/collections/field-notes/" in xml
    assert "http://testserver/themes/night/" in xml
    assert f"http://testserver/collections/{empty_collection.slug}/" not in xml
    assert "http://testserver/themes/secret/" not in xml
    assert '<meta name="robots" content="noindex, follow">' not in collection_index_html
    assert client.get(f"/collections/{empty_collection.slug}/").status_code == 404
    assert client.get("/themes/secret/").status_code == 404


def test_dynamic_social_cards_are_pngs_with_long_lived_caching(client, live_poem):
    poem_html = client.get("/poems/small-hours/").content.decode()
    poem_card_path = urlparse(meta_content(poem_html, "og:image")).path
    poem_card = client.get(poem_card_path)

    assert poem_card.status_code == 200
    assert poem_card["Content-Type"] == "image/png"
    assert poem_card["Content-Disposition"] == 'inline; filename="social-card.png"'
    assert "public" in poem_card["Cache-Control"]
    assert "max-age=31536000" in poem_card["Cache-Control"]
    assert "immutable" in poem_card["Cache-Control"]
    assert Image.open(BytesIO(poem_card.content)).size == (1200, 630)

    home_html = client.get("/").content.decode()
    site_card_path = urlparse(meta_content(home_html, "og:image")).path
    site_card = client.get(site_card_path)
    assert site_card.status_code == 200
    assert Image.open(BytesIO(site_card.content)).size == (1200, 630)


def test_dynamic_social_card_does_not_expose_draft_poems(client, site_tree):
    draft = PoemPage(title="Not Yet", slug="not-yet", poem_body="Still becoming.", live=False)
    site_tree["poem_index"].add_child(instance=draft)
    draft.save_revision()

    assert client.get(f"/og/poems/{draft.pk}/000000000000.png").status_code == 404
    assert client.get(f"/share/poems/{draft.pk}/000000000000/instagram.png").status_code == 404


def test_public_instagram_card_is_full_size_downloadable_and_unlisted(client, live_poem):
    version = instagram_card_version(
        live_poem.pk,
        live_poem.title,
        live_poem.poem_body,
        live_poem.dedication,
        "Cesar Garza",
    )
    card_path = f"/share/poems/{live_poem.pk}/{version}/instagram.png"
    response = client.get(card_path)

    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response["Content-Disposition"] == 'inline; filename="small-hours-instagram.png"'
    assert response["X-Robots-Tag"] == "noindex, noimageindex"
    assert "public" in response["Cache-Control"]
    assert "max-age=31536000" in response["Cache-Control"]
    assert "immutable" in response["Cache-Control"]
    assert Image.open(BytesIO(response.content)).size == (1080, 1350)

    download = client.get(card_path, {"download": "1"})
    assert download["Content-Disposition"] == 'attachment; filename="small-hours-instagram.png"'

    poem_html = client.get("/poems/small-hours/").content.decode()
    assert card_path not in poem_html
    assert card_path not in client.get("/sitemap.xml").content.decode()
    assert client.get(f"/share/poems/{live_poem.pk}/000000000000/instagram.png").status_code == 404

    changed_version = instagram_card_version(
        live_poem.pk,
        live_poem.title,
        f"{live_poem.poem_body}\nA new line.",
        live_poem.dedication,
        "Cesar Garza",
    )
    assert changed_version != version


def test_instagram_layout_preserves_stanzas_and_autosizes_for_more_text():
    short_layout = instagram_card_layout(
        "Small Hours",
        "The moon keeps quiet.\n\nSo do I.",
    )
    longer_layout = instagram_card_layout(
        "Small Hours",
        "\n\n".join(
            f"Line {number} carries a little more weather into the room." for number in range(1, 13)
        ),
    )

    assert short_layout.body_font_size == INSTAGRAM_BODY_MAX_SIZE
    assert "" in short_layout.body_lines
    assert longer_layout.body_font_size < short_layout.body_font_size
    assert longer_layout.body_top + longer_layout.body_height <= 1182


def test_instagram_layout_refuses_unreadably_long_single_card():
    poem_body = "\n".join(f"Line {number}" for number in range(100))

    with pytest.raises(InstagramCardTooLong, match="more than one"):
        instagram_card_layout("A Long Poem", poem_body)
