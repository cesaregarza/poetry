from django.conf import settings
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.sitemap_generator import Sitemap as WagtailSitemap
from wagtail.contrib.sitemaps.views import sitemap
from wagtail.documents import urls as wagtaildocs_urls

from poems import views
from poems.feeds import PoemFeed
from poems.sitemaps import PoetryHubSitemap

SITEMAPS = {
    "poetry_hubs": PoetryHubSitemap,
    "wagtail": WagtailSitemap,
}

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("readyz", views.readyz, name="readyz"),
    path("og/site/<str:version>.png", views.site_social_card, name="site_social_card"),
    path(
        "og/poems/<int:page_id>/<str:version>.png",
        views.poem_social_card,
        name="poem_social_card",
    ),
    path(
        "share/poems/<int:page_id>/<str:version>/instagram.png",
        views.poem_instagram_card,
        name="poem_instagram_card",
    ),
    path(
        "admin/poems/<int:page_id>/social-preview/open-graph.png",
        views.admin_poem_social_card_preview,
        name="admin_poem_social_card_preview",
    ),
    path(
        "admin/poems/<int:page_id>/social-preview/instagram.png",
        views.admin_poem_instagram_card_preview,
        name="admin_poem_instagram_card_preview",
    ),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("collections/", views.collection_index, name="collection_index"),
    path("collections/<slug:slug>/", views.collection_detail, name="collection_detail"),
    path("themes/<slug:slug>/", views.theme_detail, name="theme_detail"),
    path("search/", views.search, name="search"),
    path("feed/", PoemFeed(), name="poem_feed"),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("robots.txt", views.robots, name="robots"),
]

if settings.DEBUG:
    urlpatterns += [
        path(
            f"{settings.MEDIA_URL.lstrip('/')}<path:path>",
            views.debug_media,
            name="debug_media",
        )
    ]

urlpatterns += [path("", include(wagtail_urls))]
