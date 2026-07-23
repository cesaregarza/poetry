import importlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import clear_url_caches, resolve
from wagtail.models import (
    GroupPagePermission,
    Page,
    PageViewRestriction,
    Site,
    get_default_page_content_type,
)
from wagtail.permission_policies.pages import PagePermissionPolicy

from poems.models import AboutPage, Collection, HomePage, PoemIndexPage, PoemPage, live_poems

pytestmark = pytest.mark.django_db


def add_poem(parent, *, title, slug, body="line one\n\nline two", live=True, **kwargs):
    poem = PoemPage(
        title=title,
        slug=slug,
        poem_body=body,
        live=False,
        **kwargs,
    )
    parent.add_child(instance=poem)
    revision = poem.save_revision()
    if live:
        revision.publish()
    poem.refresh_from_db()
    return poem


def test_bootstrap_site_is_idempotent():
    call_command("bootstrap_site", hostname="testserver", port=80)
    call_command("bootstrap_site", hostname="testserver", port=80)

    assert HomePage.objects.count() == 1
    assert PoemIndexPage.objects.count() == 1
    assert AboutPage.objects.count() == 1
    assert Site.objects.get(hostname="testserver", port=80).is_default_site


def test_seeded_site_has_intentional_empty_states(client, site_tree):
    expected = {
        "/": "The first poem is still finding its shape.",
        "/poems/": "The archive is waiting for its first published poem.",
        "/collections/": "Collections will appear as the archive grows.",
        "/about/": "A note about the poet will appear here.",
    }
    for path, message in expected.items():
        response = client.get(path)
        assert response.status_code == 200
        assert message in response.content.decode()


def test_draft_is_not_public_and_owner_is_retained(client, site_tree):
    owner = get_user_model().objects.create_user(username="owner", password="safe-test-password")
    published = add_poem(site_tree["poem_index"], title="Published", slug="published", owner=owner)
    draft = add_poem(
        site_tree["poem_index"],
        title="Private Draft",
        slug="private-draft",
        owner=owner,
        live=False,
    )

    assert published.owner == owner
    assert draft.owner == owner
    assert client.get("/poems/published/").status_code == 200
    assert client.get("/poems/private-draft/").status_code == 404
    archive = client.get("/poems/").content.decode()
    assert "Published" in archive
    assert "Private Draft" not in archive


def test_public_poems_are_ordered_by_effective_date_without_reordering_admin_tree(
    client, site_tree
):
    older = add_poem(
        site_tree["poem_index"],
        title="Older dated poem",
        slug="older-dated-poem",
        display_date=date(2025, 11, 29),
    )
    same_day_earlier = add_poem(
        site_tree["poem_index"],
        title="Same day, published earlier",
        slug="same-day-published-earlier",
        display_date=date(2026, 7, 22),
    )
    same_day_later = add_poem(
        site_tree["poem_index"],
        title="Same day, published later",
        slug="same-day-published-later",
        display_date=date(2026, 7, 22),
    )
    same_timestamp_later_pk = add_poem(
        site_tree["poem_index"],
        title="Same timestamp, later ID",
        slug="same-timestamp-later-id",
        display_date=date(2026, 7, 22),
    )
    publication_date_fallback = add_poem(
        site_tree["poem_index"],
        title="Publication date fallback",
        slug="publication-date-fallback",
    )

    Page.objects.filter(pk=same_day_earlier.pk).update(
        first_published_at=datetime(2026, 7, 22, 14, tzinfo=UTC)
    )
    Page.objects.filter(pk=same_day_later.pk).update(
        first_published_at=datetime(2026, 7, 22, 15, tzinfo=UTC)
    )
    Page.objects.filter(pk=same_timestamp_later_pk.pk).update(
        first_published_at=datetime(2026, 7, 22, 15, tzinfo=UTC)
    )
    Page.objects.filter(pk=publication_date_fallback.pk).update(
        first_published_at=datetime(2026, 7, 23, 14, tzinfo=UTC)
    )

    expected_public_order = [
        "Publication date fallback",
        "Same timestamp, later ID",
        "Same day, published later",
        "Same day, published earlier",
        "Older dated poem",
    ]
    poem_ids = [
        older.pk,
        same_day_earlier.pk,
        same_day_later.pk,
        same_timestamp_later_pk.pk,
        publication_date_fallback.pk,
    ]
    assert (
        list(live_poems().filter(pk__in=poem_ids).values_list("title", flat=True))
        == expected_public_order
    )

    previous_poem, next_poem = same_day_later.get_public_neighbors()
    assert previous_poem.pk == same_timestamp_later_pk.pk
    assert next_poem.pk == same_day_earlier.pk
    assert publication_date_fallback.get_public_neighbors()[0] is None
    assert older.get_public_neighbors()[1] is None

    for path in ["/", "/poems/"]:
        listing = client.get(path).content.decode()
        assert [listing.index(f">{title}</a>") for title in expected_public_order] == sorted(
            listing.index(f">{title}</a>") for title in expected_public_order
        )

    assert list(site_tree["poem_index"].get_children().values_list("title", flat=True)) == [
        "Older dated poem",
        "Same day, published earlier",
        "Same day, published later",
        "Same timestamp, later ID",
        "Publication date fallback",
    ]


def test_poem_navigation_follows_public_order_and_skips_drafts(client, site_tree):
    older = add_poem(
        site_tree["poem_index"],
        title="Older neighbor",
        slug="older-neighbor",
        display_date=date(2026, 1, 1),
    )
    draft = add_poem(
        site_tree["poem_index"],
        title="Hidden draft",
        slug="hidden-draft",
        display_date=date(2026, 1, 2),
        live=False,
    )
    current = add_poem(
        site_tree["poem_index"],
        title="Current poem",
        slug="current-poem",
        display_date=date(2026, 1, 2),
    )
    restricted = add_poem(
        site_tree["poem_index"],
        title="Restricted poem",
        slug="restricted-poem",
        display_date=date(2026, 1, 2),
    )
    PageViewRestriction.objects.create(
        page=restricted,
        restriction_type=PageViewRestriction.PASSWORD,
        password="test-only",
    )
    newer = add_poem(
        site_tree["poem_index"],
        title="Newer neighbor",
        slug="newer-neighbor",
        display_date=date(2026, 1, 3),
    )

    previous_poem, next_poem = current.get_public_neighbors()
    assert previous_poem.pk == newer.pk
    assert next_poem.pk == older.pk
    assert draft.get_public_neighbors() == (None, None)
    assert restricted.get_public_neighbors() == (None, None)

    current_page = client.get("/poems/current-poem/")
    html = current_page.content.decode()
    assert current_page.context["previous_poem"].pk == newer.pk
    assert current_page.context["next_poem"].pk == older.pk
    assert 'href="/poems/newer-neighbor/" rel="prev"' in html
    assert 'href="/poems/older-neighbor/" rel="next"' in html
    assert "Hidden draft" not in html
    assert "Restricted poem" not in html

    newest_page = client.get("/poems/newer-neighbor/").content.decode()
    assert 'rel="prev"' not in newest_page
    assert 'href="/poems/current-poem/" rel="next"' in newest_page

    oldest_page = client.get("/poems/older-neighbor/").content.decode()
    assert 'href="/poems/current-poem/" rel="prev"' in oldest_page
    assert 'rel="next"' not in oldest_page


def test_wagtail_owner_can_edit_only_owned_poems_and_cannot_publish_without_permission(
    client, site_tree
):
    user_model = get_user_model()
    owner = user_model.objects.create_user(username="poet", password="safe-test-password")
    other = user_model.objects.create_user(username="other", password="safe-test-password")
    owned_poem = add_poem(
        site_tree["poem_index"],
        title="Owned Draft",
        slug="owned-draft",
        owner=owner,
        live=False,
    )
    other_poem = add_poem(
        site_tree["poem_index"],
        title="Another Draft",
        slug="another-draft",
        owner=other,
        live=False,
    )

    adders = Group.objects.create(name="Poem authors")
    owner.groups.add(adders)
    page_content_type = get_default_page_content_type()
    GroupPagePermission.objects.create(
        group=adders,
        page=site_tree["poem_index"],
        permission=Permission.objects.get(
            content_type=page_content_type,
            codename="add_page",
        ),
    )

    policy = PagePermissionPolicy()
    assert policy.user_has_permission_for_instance(owner, "change", owned_poem)
    assert not policy.user_has_permission_for_instance(owner, "change", other_poem)
    assert not policy.user_has_permission_for_instance(owner, "publish", owned_poem)

    owner.user_permissions.add(Permission.objects.get(codename="access_admin"))
    client.force_login(owner)
    assert client.get(f"/admin/pages/{owned_poem.pk}/edit/").status_code == 200
    assert client.get(f"/admin/pages/{other_poem.pk}/edit/").status_code != 200

    GroupPagePermission.objects.create(
        group=adders,
        page=site_tree["poem_index"],
        permission=Permission.objects.get(
            content_type=page_content_type,
            codename="publish_page",
        ),
    )
    delattr(owner, "_page_permission_cache")
    assert policy.user_has_permission_for_instance(owner, "publish", owned_poem)


def test_exact_text_is_escaped_and_whitespace_is_preserved(client, site_tree):
    body = "\tFirst <script>alert('x')</script>\r\n\r\n  café — 雨\r\n" + ("unbroken" * 50)
    poem = add_poem(site_tree["poem_index"], title="Exact", slug="exact", body=body)

    poem.refresh_from_db()
    assert poem.poem_body == body
    html = client.get("/poems/exact/").content.decode()
    assert "<script>" not in html
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;" in html
    assert "\r\n\r\n  café — 雨\r\n" in html
    assert 'class="poem-text"' in html


def test_collection_theme_search_and_listing_filters(client, site_tree):
    collection = Collection.objects.create(name="Field Notes")
    rain = add_poem(
        site_tree["poem_index"],
        title="Rain Ledger",
        slug="rain-ledger",
        body="rain writes against the window",
        collection=collection,
        display_date=date(2026, 1, 2),
    )
    rain.themes.add("weather")
    rain.save_revision().publish()
    add_poem(
        site_tree["poem_index"],
        title="Stone",
        slug="stone",
        body="an unmoving afternoon",
    )

    assert "Rain Ledger" in client.get("/collections/field-notes/").content.decode()
    assert "Rain Ledger" in client.get("/themes/weather/").content.decode()
    assert "Rain Ledger" in client.get("/search/", {"q": "window"}).content.decode()
    filtered = client.get("/poems/", {"collection": "field-notes"}).content.decode()
    assert "Rain Ledger" in filtered
    assert ">Stone<" not in filtered


def test_collection_navigation_waits_for_a_publicly_collected_poem(client, site_tree):
    empty_collection = Collection.objects.create(name="Empty Collection")
    draft_collection = Collection.objects.create(name="Draft Collection")
    restricted_collection = Collection.objects.create(name="Restricted Collection")
    draft = add_poem(
        site_tree["poem_index"],
        title="Collected Draft",
        slug="collected-draft",
        collection=draft_collection,
        live=False,
    )
    add_poem(
        site_tree["poem_index"],
        title="Public but Uncollected",
        slug="public-but-uncollected",
    )
    restricted = add_poem(
        site_tree["poem_index"],
        title="Restricted Collection Poem",
        slug="restricted-collection-poem",
        collection=restricted_collection,
    )
    PageViewRestriction.objects.create(
        page=restricted,
        restriction_type=PageViewRestriction.PASSWORD,
        password="test-only",
    )

    home = client.get("/").content.decode()
    archive = client.get("/poems/").content.decode()
    assert 'href="/collections/"' not in home
    assert 'id="archive-collection"' not in archive

    collection_index = client.get("/collections/")
    assert collection_index.status_code == 200
    assert empty_collection.name in collection_index.content.decode()
    assert draft_collection.name in collection_index.content.decode()
    assert restricted_collection.name in collection_index.content.decode()
    assert client.get(f"/collections/{draft_collection.slug}/").status_code == 200

    draft.save_revision().publish()

    home = client.get("/").content.decode()
    archive = client.get("/poems/").content.decode()
    assert 'href="/collections/"' in home
    assert 'id="archive-collection"' in archive
    assert f'<option value="{draft_collection.slug}">' in archive
    assert f'<option value="{empty_collection.slug}">' not in archive
    assert f'<option value="{restricted_collection.slug}">' not in archive


def test_feed_sitemap_robots_and_metadata(client, site_tree, live_poem):
    feed = client.get("/feed/")
    assert feed.status_code == 200
    assert b"Small Hours" in feed.content

    sitemap = client.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert b"/poems/small-hours/" in sitemap.content

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert b"Disallow: /admin/" in robots.content
    assert b"Sitemap: http://testserver/sitemap.xml" in robots.content

    poem = client.get("/poems/small-hours/").content.decode()
    assert '<meta property="og:type" content="article">' in poem
    assert "A poem about the attentive night." in poem


def test_health_is_database_independent_and_readiness_queries_database(client, site_tree):
    with CaptureQueriesContext(connection) as health_queries:
        health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert len(health_queries) == 0

    with CaptureQueriesContext(connection) as readiness_queries:
        readiness = client.get("/readyz")
    assert readiness.status_code == 200
    assert readiness.json() == {"status": "ok"}
    assert len(readiness_queries) == 1


def test_wagtail_admin_is_the_only_admin_route(client, site_tree):
    admin = client.get("/admin/")
    assert admin.status_code == 302
    assert "/admin/login/" in admin["Location"]
    assert client.get("/django-admin/").status_code == 404


def test_debug_media_route_serves_local_uploads(client, settings, tmp_path):
    import poetry_site.urls as project_urls

    original_debug = settings.DEBUG
    original_media_root = settings.MEDIA_ROOT
    settings.DEBUG = True
    settings.MEDIA_ROOT = tmp_path
    importlib.reload(project_urls)
    clear_url_caches()
    media_root = Path(settings.MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)
    test_file = media_root / "local-media-check.txt"
    test_file.write_text("local media works", encoding="utf-8")
    try:
        match = resolve("/media/local-media-check.txt")
        assert match.url_name == "debug_media"
        assert test_file.is_file()
        response = client.get("/media/local-media-check.txt")
    finally:
        test_file.unlink(missing_ok=True)
        settings.DEBUG = original_debug
        settings.MEDIA_ROOT = original_media_root
        importlib.reload(project_urls)
        clear_url_caches()

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"local media works"


def test_page_tree_is_restricted_to_expected_types(site_tree):
    assert HomePage.allowed_subpage_models() == [PoemIndexPage, AboutPage]
    assert PoemIndexPage.allowed_subpage_models() == [PoemPage]
    assert PoemPage.allowed_subpage_models() == []
    assert Page.objects.get(pk=site_tree["home"].pk).specific_class is HomePage
