from django.conf import settings
from django.core.paginator import Paginator
from django.db import DatabaseError, connections
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.static import serve
from taggit.models import Tag

from poems.models import Collection, live_poems


def paginate(request, queryset, per_page=12):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page"))


def collection_index(request):
    collections = Collection.objects.order_by("name")
    return render(request, "poems/collection_index.html", {"collections": collections})


def collection_detail(request, slug):
    collection = get_object_or_404(Collection, slug=slug)
    poems = paginate(request, live_poems().filter(collection=collection))
    return render(
        request,
        "poems/collection_detail.html",
        {"collection": collection, "poems": poems},
    )


def theme_detail(request, slug):
    theme = get_object_or_404(Tag, slug=slug)
    poems = paginate(request, live_poems().filter(themes=theme).distinct())
    return render(request, "poems/theme_detail.html", {"theme": theme, "poems": poems})


def search(request):
    query = request.GET.get("q", "").strip()
    poems = live_poems()
    poems = poems.search(query) if query else poems.none()
    return render(
        request,
        "poems/search_results.html",
        {"query": query, "poems": paginate(request, poems)},
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


def debug_media(request, path):
    if not settings.DEBUG:
        raise Http404
    return serve(request, path, document_root=settings.MEDIA_ROOT)
