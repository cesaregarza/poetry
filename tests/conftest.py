from datetime import date

import pytest
from django.core.management import call_command

from poems.models import AboutPage, HomePage, PoemIndexPage, PoemPage


@pytest.fixture
def site_tree(db):
    call_command("bootstrap_site", hostname="testserver", port=80, verbosity=0)
    return {
        "home": HomePage.objects.get(),
        "poem_index": PoemIndexPage.objects.get(),
        "about": AboutPage.objects.get(),
    }


@pytest.fixture
def live_poem(site_tree):
    poem = PoemPage(
        title="Small Hours",
        slug="small-hours",
        display_date=date(2026, 7, 21),
        poem_body="The moon keeps quiet.\n\nSo do I.",
        listing_description="A poem about the attentive night.",
        live=False,
    )
    site_tree["poem_index"].add_child(instance=poem)
    poem.themes.add("night")
    poem.save_revision().publish()
    poem.refresh_from_db()
    return poem
