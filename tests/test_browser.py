import json
from datetime import date
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from poems.models import PoemPage

pytestmark = [
    pytest.mark.browser,
    pytest.mark.django_db(transaction=True, serialized_rollback=True),
]
AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"


def assert_wcag_clean(page):
    page.add_script_tag(path=str(AXE_PATH))
    results = page.evaluate(
        """async () => await axe.run(document, {
            runOnly: {
                type: 'tag',
                values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
            },
            resultTypes: ['violations']
        })"""
    )
    violations = [
        {
            "id": violation["id"],
            "impact": violation["impact"],
            "nodes": [node["target"] for node in violation["nodes"]],
        }
        for violation in results["violations"]
    ]
    assert violations == []


def test_system_theme_toggle_and_persistence(page, live_server, site_tree):
    page.emulate_media(color_scheme="dark")
    page.goto(live_server.url)

    assert page.locator("html").get_attribute("data-theme") == "dark"
    toggle = page.get_by_role("button", name="Use light theme")
    assert toggle.get_attribute("aria-pressed") == "true"
    assert_wcag_clean(page)

    toggle.click()
    assert page.locator("html").get_attribute("data-theme") == "light"
    assert page.evaluate("localStorage.getItem('poetry-theme')") == "light"
    assert_wcag_clean(page)

    page.reload()
    assert page.locator("html").get_attribute("data-theme") == "light"
    assert page.get_by_role("button", name="Use dark theme").is_visible()

    page.evaluate("localStorage.setItem('poetry-theme', 'dark')")
    page.emulate_media(color_scheme="light")
    page.reload()
    assert page.locator("html").get_attribute("data-theme") == "dark"


def test_keyboard_mobile_print_and_reduced_motion(page, live_server, site_tree, live_poem):
    older_poem = PoemPage(
        title="Earlier Poem with a Deliberately Long Navigation Title",
        slug="earlier-poem",
        display_date=date(2026, 7, 20),
        poem_body="An earlier line.",
        live=False,
    )
    site_tree["poem_index"].add_child(instance=older_poem)
    older_poem.save_revision().publish()

    page.set_viewport_size({"width": 360, "height": 740})
    page.goto(f"{live_server.url}/poems/small-hours/")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.get_by_role("link", name="All poems").is_visible()
    assert page.get_by_role(
        "link",
        name="Next poem: Earlier Poem with a Deliberately Long Navigation Title",
    ).is_visible()
    assert_wcag_clean(page)

    page.keyboard.press("Tab")
    assert page.locator(":focus").get_attribute("href") == "#main-content"

    page.emulate_media(media="print")
    display = page.locator(".site-header").evaluate("element => getComputedStyle(element).display")
    assert display == "none"
    navigation_display = page.locator(".poem-navigation").evaluate(
        "element => getComputedStyle(element).display"
    )
    assert navigation_display == "none"

    page.emulate_media(media="screen", reduced_motion="reduce")
    duration = page.locator("body").evaluate(
        "element => getComputedStyle(element).transitionDuration"
    )
    assert duration in {"0.00001s", "1e-05s", "0s"}


def test_wagtail_social_preview_panel_renders_both_formats(
    page,
    live_server,
    live_poem,
):
    get_user_model().objects.create_superuser(
        username="browser-admin",
        email="browser-admin@example.com",
        password="safe-test-password",
    )
    page.goto(f"{live_server.url}/admin/login/")
    page.get_by_label("Username").fill("browser-admin")
    page.get_by_label("Password").fill("safe-test-password")
    page.get_by_role("button", name="Sign in").click()

    page.goto(f"{live_server.url}/admin/pages/{live_poem.pk}/edit/")
    page.get_by_role("heading", name="Social previews").scroll_into_view_if_needed()

    open_graph = page.get_by_alt_text("Open Graph preview for Small Hours")
    instagram = page.get_by_alt_text("Instagram portrait preview for Small Hours")
    open_graph.wait_for()
    instagram.wait_for()

    assert open_graph.evaluate("image => [image.naturalWidth, image.naturalHeight]") == [
        1200,
        630,
    ]
    assert instagram.evaluate("image => [image.naturalWidth, image.naturalHeight]") == [
        1080,
        1350,
    ]
    assert page.get_by_role("link", name="Public image").count() == 2


def test_wagtail_scansion_assistant_analyzes_and_corrects_occurrences(
    page,
    live_server,
    live_poem,
):
    get_user_model().objects.create_superuser(
        username="scansion-browser-admin",
        email="scansion-browser@example.com",
        password="safe-test-password",
    )
    page.goto(f"{live_server.url}/admin/login/")
    page.get_by_label("Username").fill("scansion-browser-admin")
    page.get_by_label("Password").fill("safe-test-password")
    page.get_by_role("button", name="Sign in").click()

    page.goto(f"{live_server.url}/admin/pages/{live_poem.pk}/edit/")
    assert not page.get_by_text("Scansion overrides", exact=True).is_visible()
    page.locator("#id_poem_body").fill("Shall I compare thee to a summer day")
    page.get_by_label("Show stress assistant").check()
    page.get_by_label("Guide").select_option("iambic_pentameter")

    status = page.locator("[data-scansion-status]")
    status.get_by_text("Dictionary stress loaded", exact=False).wait_for()
    assert page.locator(".scansion-word").count() == 8
    assert page.locator(".scansion-assistant__meter").is_visible()

    easy_symbols = page.get_by_role("button", name="Easy − / +")
    traditional_symbols = page.get_by_role("button", name="Traditional ˘ / ´")
    assert easy_symbols.get_attribute("aria-pressed") == "true"
    unstressed_i = page.get_by_label("I, syllable 1: unstressed")
    assert unstressed_i.text_content() == "−"
    assert unstressed_i.evaluate("control => getComputedStyle(control).backgroundColor") not in {
        "rgba(0, 0, 0, 0)",
        "transparent",
    }

    traditional_symbols.click()
    assert traditional_symbols.get_attribute("aria-pressed") == "true"
    assert page.get_by_label("I, syllable 1: unstressed").text_content() == "˘"
    assert page.evaluate("localStorage.getItem('poetry-scansion-symbols')") == "traditional"
    easy_symbols.click()

    promoted_i = page.get_by_label("I, syllable 1: unstressed")
    assert "scansion-syllable--mismatch" in promoted_i.get_attribute("class")
    promoted_i.click()
    promoted_i = page.get_by_label("I, syllable 1: stressed")
    assert promoted_i.get_attribute("aria-pressed") == "true"
    assert "scansion-syllable--mismatch" not in promoted_i.get_attribute("class")

    saved = json.loads(page.locator("#id_scansion_overrides").input_value())
    assert saved["occurrences"]["l0:w1:i"]["stresses"] == [True]

    page.locator("#id_poem_body").fill("Quizzacious")
    status.get_by_text("need manual syllables", exact=False).wait_for()
    unknown_badge = page.get_by_role("img", name="Quizzacious: not in dictionary")
    assert unknown_badge.is_visible()
    assert unknown_badge.text_content() == "!"
    assert not page.get_by_text("Not in dictionary", exact=True).is_visible()
    page.get_by_label("Add a syllable to Quizzacious").click()
    assert page.get_by_label("Quizzacious, syllable 1: unstressed").is_visible()

    page.get_by_role("button", name="Save draft", exact=True).click()
    page.wait_for_load_state("networkidle")
    assert page.get_by_label("Show stress assistant").is_checked()
    assert page.get_by_label("Guide").input_value() == "iambic_pentameter"
    assert page.locator("#id_poem_body").input_value() == "Quizzacious"
    status.get_by_text("need manual syllables", exact=False).wait_for()
    assert page.get_by_label("Quizzacious, syllable 1: unstressed").is_visible()
