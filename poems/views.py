from django.conf import settings
from django.core.paginator import Paginator
from django.db import DatabaseError, connections
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.cache import patch_cache_control
from django.views.decorators.http import require_safe
from django.views.static import serve

from poems.models import (
    PoemPage,
    PoetrySiteSettings,
    live_poems,
    public_collections,
    public_themes,
)
from poems.seo import canonical_url
from poems.social_cards import render_social_card


def paginate(request, queryset, per_page=12):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def collection_index(request):
    collections = public_collections()
    return render(
        request,
        "poems/collection_index.html",
        {
            "collections": collections,
            "seo_noindex": not collections.exists(),
        },
    )


def collection_detail(request, slug):
    collection = get_object_or_404(public_collections(), slug=slug)
    poems = paginate(request, live_poems().filter(collection=collection))
    return render(
        request,
        "poems/collection_detail.html",
        {
            "canonical_url": canonical_url(request, page_number=poems.number),
            "collection": collection,
            "poems": poems,
        },
    )


def theme_detail(request, slug):
    theme = get_object_or_404(public_themes(), slug=slug)
    poems = paginate(request, live_poems().filter(themes=theme).distinct())
    return render(
        request,
        "poems/theme_detail.html",
        {
            "canonical_url": canonical_url(request, page_number=poems.number),
            "theme": theme,
            "poems": poems,
        },
    )


def search(request):
    query = request.GET.get("q", "").strip()
    poems = live_poems()
    poems = poems.search(query) if query else poems.none()
    return render(
        request,
        "poems/search_results.html",
        {
            "canonical_url": canonical_url(request),
            "query": query,
            "poems": paginate(request, poems),
            "seo_noindex": True,
        },
    )


def healthz(request):
    return JsonResponse({"status": "ok"})


def readyz(request):
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})


def robots(request):
    body = "User-agent: *\nAllow: /\nDisallow: /admin/\n"
    body += f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}\n"
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


def _social_card_response(*, title, eyebrow, footer):
    response = HttpResponse(
        render_social_card(title, eyebrow, footer),
        content_type="image/png",
    )
    patch_cache_control(response, public=True, max_age=31536000, immutable=True)
    response["Content-Disposition"] = 'inline; filename="social-card.png"'
    return response


@require_safe
def site_social_card(request, version):
    site_settings = PoetrySiteSettings.for_request(request)
    return _social_card_response(
        title=site_settings.site_title,
        eyebrow="Poetry",
        footer=request.get_host(),
    )


@require_safe
def poem_social_card(request, page_id, version):
    poem = get_object_or_404(PoemPage.objects.live().public(), pk=page_id)
    site_settings = PoetrySiteSettings.for_request(request)
    return _social_card_response(
        title=poem.title,
        eyebrow=f"A poem by {site_settings.author_name}",
        footer=request.get_host(),
    )


def debug_media(request, path):
    if not settings.DEBUG:
        raise Http404
    return serve(request, path, document_root=settings.MEDIA_ROOT)
