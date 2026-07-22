from django.conf import settings
from django.urls import include, path
from wagtail import urls as wagtail_urls
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.contrib.sitemaps.views import sitemap
from wagtail.documents import urls as wagtaildocs_urls

from poems import views
from poems.feeds import PoemFeed

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("readyz", views.readyz, name="readyz"),
    path("admin/", include(wagtailadmin_urls)),
    path("documents/", include(wagtaildocs_urls)),
    path("collections/", views.collection_index, name="collection_index"),
    path("collections/<slug:slug>/", views.collection_detail, name="collection_detail"),
    path("themes/<slug:slug>/", views.theme_detail, name="theme_detail"),
    path("search/", views.search, name="search"),
    path("feed/", PoemFeed(), name="poem_feed"),
    path("sitemap.xml", sitemap, name="sitemap"),
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
