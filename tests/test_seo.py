import json
import re

import pytest

from poems.models import Collection, PoemPage

pytestmark = pytest.mark.django_db


def structured_data(html, schema):
    match = re.search(
        rf'<script type="application/ld\+json" data-schema="{schema}">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert match
    return json.loads(match.group(1))


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
        assert '<meta name="robots" content="noindex, follow">' not in html


def test_poem_metadata_and_structured_data_are_specific(client, live_poem):
    html = client.get("/poems/small-hours/").content.decode()

    assert "<title>Small Hours — A Poem by Cesar Garza</title>" in html
    assert '<meta name="description" content="A poem about the attentive night.">' in html
    assert '<meta property="og:type" content="article">' in html
    assert '<meta property="og:title" content="Small Hours — A Poem by Cesar Garza">' in html
    assert '<link rel="canonical" href="http://testserver/poems/small-hours/">' in html
    assert '<meta property="article:author" content="http://testserver/about/">' in html

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
