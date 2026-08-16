import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import DatabaseError, connections
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.cache import patch_cache_control
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST, require_safe
from django.views.static import serve

from poems.models import (
    PoemPage,
    PoetrySiteSettings,
    live_poems,
    public_collections,
    public_themes,
)
from poems.scansion import MAX_POEM_LENGTH, provider
from poems.seo import canonical_url
from poems.social_cards import (
    InstagramCardTooLong,
    instagram_card_version,
    render_instagram_card,
    render_social_card,
)


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


def _png_response(payload, *, filename, public, download=False, indexable=True):
    response = HttpResponse(
        payload,
        content_type="image/png",
    )
    if public:
        patch_cache_control(response, public=True, max_age=31536000, immutable=True)
    else:
        patch_cache_control(response, private=True, no_store=True, max_age=0)
    disposition = "attachment" if download else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
    if not indexable:
        response["X-Robots-Tag"] = "noindex, noimageindex"
    return response


def _social_card_response(*, title, eyebrow, footer, public=True, download=False):
    return _png_response(
        render_social_card(title, eyebrow, footer),
        filename="social-card.png",
        public=public,
        download=download,
        indexable=public,
    )


def _instagram_card_response(request, poem, *, public):
    filename_stem = slugify(poem.slug or poem.title) or f"poem-{poem.pk}"
    try:
        payload = render_instagram_card(
            poem.title,
            poem.poem_body,
            poem.dedication,
            request.get_host(),
        )
    except InstagramCardTooLong as error:
        response = HttpResponse(
            str(error),
            status=422,
            content_type="text/plain; charset=utf-8",
        )
        patch_cache_control(response, private=True, no_store=True, max_age=0)
        response["X-Robots-Tag"] = "noindex, noimageindex"
        return response

    return _png_response(
        payload,
        filename=f"{filename_stem}-instagram.png",
        public=public,
        download=request.GET.get("download") == "1",
        indexable=False,
    )


def _editable_poem_for_request(request, page_id):
    poem = get_object_or_404(
        PoemPage.objects.select_related("latest_revision"),
        pk=page_id,
    )
    if (
        not request.user.has_perm("wagtailadmin.access_admin")
        or not poem.permissions_for_user(request.user).can_edit()
    ):
        raise PermissionDenied
    return poem.get_latest_revision_as_object().specific


@require_POST
@login_required(login_url="/admin/login/")
@never_cache
def admin_poem_scansion_analysis(request):
    if not request.user.has_perm("wagtailadmin.access_admin"):
        raise PermissionDenied

    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Request body must be valid JSON."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Request body must be a JSON object."}, status=400)

    text = payload.get("text")
    mode = payload.get("mode", "general")
    page_id = payload.get("page_id")
    if not isinstance(text, str):
        return JsonResponse({"error": "Poem text must be a string."}, status=400)
    if len(text) > MAX_POEM_LENGTH:
        return JsonResponse(
            {"error": f"Poem text cannot exceed {MAX_POEM_LENGTH:,} characters."},
            status=413,
        )
    if mode not in {"general", "iambic_pentameter"}:
        return JsonResponse({"error": "Unsupported scansion mode."}, status=400)
    if page_id is not None:
        try:
            page_id = int(page_id)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid poem page identifier."}, status=400)
        _editable_poem_for_request(request, page_id)

    response = JsonResponse(provider.analyze(text, mode=mode))
    patch_cache_control(response, private=True, no_store=True, max_age=0)
    response["X-Robots-Tag"] = "noindex"
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


@require_safe
def poem_instagram_card(request, page_id, version):
    poem = get_object_or_404(PoemPage.objects.live().public(), pk=page_id)
    expected_version = instagram_card_version(
        poem.pk,
        poem.title,
        poem.poem_body,
        poem.dedication,
        request.get_host(),
    )
    if version != expected_version:
        raise Http404
    return _instagram_card_response(request, poem, public=True)


@require_safe
@login_required(login_url="/admin/login/")
def admin_poem_social_card_preview(request, page_id):
    poem = _editable_poem_for_request(request, page_id)
    site_settings = PoetrySiteSettings.for_request(request)
    return _social_card_response(
        title=poem.title,
        eyebrow=f"A poem by {site_settings.author_name}",
        footer=request.get_host(),
        public=False,
        download=request.GET.get("download") == "1",
    )


@require_safe
@login_required(login_url="/admin/login/")
def admin_poem_instagram_card_preview(request, page_id):
    poem = _editable_poem_for_request(request, page_id)
    return _instagram_card_response(request, poem, public=False)


def debug_media(request, path):
    if not settings.DEBUG:
        raise Http404
    return serve(request, path, document_root=settings.MEDIA_ROOT)
