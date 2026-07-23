from datetime import date
from pathlib import Path

import pytest

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
