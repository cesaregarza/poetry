from django.contrib.syndication.views import Feed
from django.utils.html import escape

from poems.models import live_poems


class PoemFeed(Feed):
    title = "Cesar Garza — Poetry"
    link = "/poems/"
    description = "New poems by Cesar Garza"

    def items(self):
        return live_poems()[:20]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return escape(item.listing_description)

    def item_link(self, item):
        return item.full_url

    def item_pubdate(self, item):
        return item.first_published_at

    def item_author_name(self, item):
        return "Cesar Garza"
