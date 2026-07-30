from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from poems.models import public_collections, public_themes


class PoetryHubSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        collections = list(public_collections())
        locations = []
        if collections:
            locations.append(reverse("collection_index"))
            locations.extend(
                reverse("collection_detail", kwargs={"slug": collection.slug})
                for collection in collections
            )
        locations.extend(
            reverse("theme_detail", kwargs={"slug": theme.slug}) for theme in public_themes()
        )
        return locations

    def location(self, item):
        return item
