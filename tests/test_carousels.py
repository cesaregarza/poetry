from io import BytesIO
from zipfile import ZipFile

import pytest
from django.contrib.auth import get_user_model
from PIL import Image, ImageDraw

from poems.models import PoemPage
from poems.social_cards import (
    INSTAGRAM_BODY_MAX_SIZE,
    INSTAGRAM_BODY_MIN_SIZE,
    INSTAGRAM_CAROUSEL_MAX_SLIDES,
    INSTAGRAM_CAROUSEL_PREFERRED_MIN_SIZE,
    InstagramCardTooLong,
    _font,
    instagram_card_layout,
    instagram_carousel_layouts,
    render_instagram_card,
    render_instagram_slide,
)

LONG_BODY = "\n\n".join(
    "\n".join(f"Stanza {stanza}, line {line}." for line in range(1, 5)) for stanza in range(1, 11)
)


def test_short_poem_keeps_original_card():
    args = ("Small Hours", "The moon keeps quiet.\n\nSo do I.", "a friend")
    assert instagram_carousel_layouts(*args) == (instagram_card_layout(*args),)
    assert render_instagram_slide(*args, "poetry.cegarza.com", 1) == render_instagram_card(
        *args, "poetry.cegarza.com"
    )


def test_carousel_preserves_complete_stanzas_and_readable_layout():
    layouts = instagram_carousel_layouts("A Long Poem", LONG_BODY, "a friend")
    assert 1 < len(layouts) <= INSTAGRAM_CAROUSEL_MAX_SLIDES
    assert len(layouts) <= 3
    assert len({layout.body_font_size for layout in layouts}) == 1
    assert layouts[0].body_font_size >= INSTAGRAM_CAROUSEL_PREFERRED_MIN_SIZE
    assert [line for layout in layouts for line in layout.body_lines if line] == [
        line for line in LONG_BODY.splitlines() if line
    ]
    for stanza in LONG_BODY.split("\n\n"):
        assert any(stanza in "\n".join(layout.body_lines) for layout in layouts)
    for layout in layouts:
        assert layout.body_top + layout.body_height <= 1182
        assert layout.body_lines[0] and layout.body_lines[-1]
        assert layout.dedication_lines == ("for a friend",)


def test_medium_poem_fits_two_slides_without_splitting_stanzas():
    # Uneven stanzas should not create an extra slide just to retain oversized type.
    body = "\n\n".join(
        "\n".join(f"Stanza {stanza}, line {line}." for line in range(length))
        for stanza, length in enumerate((1, 2, 4, 8, 16, 6))
    )
    layouts = instagram_carousel_layouts("A title of ordinary length", body)
    assert len(layouts) == 2
    assert layouts[0].body_font_size >= INSTAGRAM_CAROUSEL_PREFERRED_MIN_SIZE
    for stanza in body.split("\n\n"):
        assert any(stanza in "\n".join(layout.body_lines) for layout in layouts)


def test_oversized_stanza_splits_without_lost_or_duplicated_lines():
    body = "\n".join(f"  Line {number}: café — rain." for number in range(100))
    layouts = instagram_carousel_layouts("Long stanza", body)
    assert [line for layout in layouts for line in layout.body_lines] == body.splitlines()
    assert len({layout.body_top for layout in layouts}) == 1


def test_carousel_wraps_long_lines_and_handles_crlf_tabs_and_blank_edges():
    line = "\t" + "A word of weather. " * 80 + "end."
    body = "\r\n\r\n" + "\r\n \t\r\n".join([line] * 4) + "\r\n\r\n"
    layouts = instagram_carousel_layouts("Weather", body)
    rendered = [line for layout in layouts for line in layout.body_lines]
    assert " ".join(" ".join(rendered).split()) == " ".join(body.split())
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for layout in layouts:
        font = _font("SourceSerif4Variable-Roman.woff2", layout.body_font_size)
        assert all(draw.textlength(line, font=font) <= 848 for line in layout.body_lines)
        assert layout.body_top + layout.body_height <= 1182
        assert layout.body_lines[0].strip() and layout.body_lines[-1].strip()


def test_carousel_reduces_size_to_stay_within_slide_limit_and_never_truncates():
    body = "\n".join(f"Line {number}" for number in range(400))
    layouts = instagram_carousel_layouts("Many lines", body)
    assert len(layouts) <= INSTAGRAM_CAROUSEL_MAX_SLIDES
    assert INSTAGRAM_BODY_MIN_SIZE <= layouts[0].body_font_size < INSTAGRAM_BODY_MAX_SIZE
    assert [line for layout in layouts for line in layout.body_lines] == body.splitlines()
    with pytest.raises(InstagramCardTooLong, match="exceeds 20 slides"):
        instagram_carousel_layouts("Too many lines", "a\n" * 1000)


@pytest.mark.parametrize("title,dedication", [("W" * 200, ""), ("Title", "W" * 200)])
def test_unfittable_header_is_reported_instead_of_clipped(title, dedication):
    with pytest.raises(InstagramCardTooLong):
        instagram_carousel_layouts(title, LONG_BODY, dedication)


@pytest.fixture
def carousel_poem(site_tree):
    poem = PoemPage(title="Long Weather", slug="long-weather", poem_body="Live text.", live=False)
    site_tree["poem_index"].add_child(instance=poem)
    poem.save_revision().publish()
    poem.poem_body = LONG_BODY
    poem.save_revision()
    return poem


@pytest.fixture
def carousel_admin(client):
    admin = get_user_model().objects.create_superuser(
        username="carousel-admin", password="safe-test-password"
    )
    client.force_login(admin)
    return admin


def test_carousel_panel_and_zip_use_saved_draft_without_publishing(
    client, carousel_poem, carousel_admin
):
    poem = carousel_poem
    base = f"/admin/poems/{poem.pk}/social-preview"
    count = len(instagram_carousel_layouts(poem.title, poem.poem_body, poem.dedication))
    html = client.get(f"/admin/pages/{poem.pk}/edit/").content.decode()
    assert f"Your carousel is ready: {count} slides." in html
    assert "This poem needs a carousel" not in html
    assert f"{base}/instagram.zip" in html
    for number in range(1, count + 1):
        assert f"{base}/instagram/{number}.png" in html

    response = client.get(f"{base}/instagram.zip")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/zip"
    assert response["Content-Disposition"] == (
        'attachment; filename="long-weather-instagram-carousel.zip"'
    )
    assert "private" in response["Cache-Control"]
    assert "no-store" in response["Cache-Control"]
    assert response["X-Robots-Tag"] == "noindex, noimageindex"
    with ZipFile(BytesIO(response.content)) as archive:
        assert archive.namelist() == [
            f"long-weather-instagram-{number:02d}.png" for number in range(1, count + 1)
        ]
        for number, name in enumerate(archive.namelist(), start=1):
            payload = archive.read(name)
            assert Image.open(BytesIO(payload)).size == (1080, 1350)
            slide = client.get(f"{base}/instagram/{number}.png", {"download": "1"})
            assert slide.status_code == 200
            assert slide.content == payload
            assert slide.content == render_instagram_slide(
                poem.title, LONG_BODY, poem.dedication, "testserver", number
            )
            assert slide["Content-Disposition"] == f'attachment; filename="{name}"'
            assert "no-store" in slide["Cache-Control"]
            assert slide["X-Robots-Tag"] == "noindex, noimageindex"
    poem.refresh_from_db()
    assert poem.poem_body == "Live text."
    assert "Stanza 1" not in client.get("/poems/long-weather/").content.decode()

    # A newly saved revision must invalidate layouts and rendered slide bytes.
    poem.poem_body = "A short replacement."
    poem.save_revision()
    response = client.get(f"{base}/instagram.zip")
    with ZipFile(BytesIO(response.content)) as archive:
        assert len(archive.namelist()) == 1
        assert archive.read(archive.namelist()[0]) == render_instagram_card(
            poem.title, poem.poem_body, poem.dedication, "testserver"
        )
    assert client.get(f"{base}/instagram/2.png").status_code == 404


@pytest.mark.parametrize("suffix", ["instagram.zip", "instagram/1.png"])
def test_carousel_requires_login_and_permission_to_edit(client, carousel_poem, suffix):
    path = f"/admin/poems/{carousel_poem.pk}/social-preview/{suffix}"
    assert client.get(path).status_code == 302
    user = get_user_model().objects.create_user(username="stranger")
    client.force_login(user)
    assert client.get(path).status_code == 403
    # Access to admin alone does not grant access to another author's draft.
    from django.contrib.auth.models import Permission

    user.user_permissions.add(Permission.objects.get(codename="access_admin"))
    assert client.get(path).status_code == 403


def test_invalid_slide_and_unexportable_poem(client, carousel_poem, carousel_admin):
    base = f"/admin/poems/{carousel_poem.pk}/social-preview"
    for number in (0, 999):
        assert client.get(f"{base}/instagram/{number}.png").status_code == 404
    assert client.post(f"{base}/instagram.zip").status_code == 405
    carousel_poem.title = "W" * 200
    carousel_poem.save_revision()
    for suffix in ("instagram.zip", "instagram/1.png"):
        response = client.get(f"{base}/{suffix}")
        assert response.status_code == 422
        assert "no-store" in response["Cache-Control"]
    html = client.get(f"/admin/pages/{carousel_poem.pk}/edit/").content.decode()
    assert "Instagram export needs attention" in html
    assert "Download carousel ZIP" not in html
