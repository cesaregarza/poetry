from django.db import models
from django.db.models.functions import Cast, Coalesce
from django.utils.text import slugify
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from taggit.models import Tag, TaggedItemBase
from wagtail.admin.panels import FieldPanel, MultiFieldPanel
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting
from wagtail.fields import RichTextField
from wagtail.models import Page
from wagtail.search import index
from wagtail.snippets.models import register_snippet

from poems.seo import absolute_site_url, canonical_url, serialize_json_ld


@register_snippet
class Collection(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = RichTextField(
        blank=True,
        features=["bold", "italic", "link"],
        help_text="A short introduction shown on the collection page.",
    )

    panels = [
        FieldPanel("name"),
        FieldPanel("slug"),
        FieldPanel("description"),
    ]

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class PoemPageTag(TaggedItemBase):
    content_object = ParentalKey(
        "poems.PoemPage",
        related_name="tagged_items",
        on_delete=models.CASCADE,
    )


@register_setting(icon="site")
class PoetrySiteSettings(BaseSiteSetting):
    site_title = models.CharField(max_length=120, default="Cesar Garza — Poetry")
    author_name = models.CharField(max_length=100, default="Cesar Garza")
    introduction = RichTextField(
        blank=True,
        default=("<p>A place for poems, fragments, and the silence that surrounds them.</p>"),
        features=["bold", "italic", "link"],
    )
    website_url = models.URLField(blank=True)
    mastodon_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    default_social_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    panels = [
        MultiFieldPanel(
            [
                FieldPanel("site_title"),
                FieldPanel("author_name"),
                FieldPanel("introduction"),
                FieldPanel("default_social_image"),
            ],
            heading="Identity",
        ),
        MultiFieldPanel(
            [
                FieldPanel("website_url"),
                FieldPanel("mastodon_url"),
                FieldPanel("instagram_url"),
            ],
            heading="Elsewhere",
        ),
    ]


class HomePage(Page):
    max_count = 1
    parent_page_types = ["wagtailcore.Page"]
    subpage_types = ["poems.PoemIndexPage", "poems.AboutPage"]
    template = "poems/home_page.html"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        poems = live_poems()
        context["featured_poems"] = poems.filter(featured=True)[:3]
        context["latest_poems"] = poems[:6]
        return context


class PoemIndexPage(Page):
    intro = RichTextField(blank=True, features=["bold", "italic", "link"])

    parent_page_types = ["poems.HomePage"]
    subpage_types = ["poems.PoemPage"]
    template = "poems/poem_index_page.html"

    content_panels = Page.content_panels + [FieldPanel("intro")]

    def get_context(self, request, *args, **kwargs):
        from poems.views import paginate

        context = super().get_context(request, *args, **kwargs)
        poems = live_poems().descendant_of(self)
        query = request.GET.get("q", "").strip()
        collection = request.GET.get("collection", "").strip()
        theme = request.GET.get("theme", "").strip()
        if collection:
            poems = poems.filter(collection__slug=collection)
        if theme:
            poems = poems.filter(themes__slug=theme)
        if query:
            poems = poems.search(query)
        poems = paginate(request, poems, per_page=12)
        context.update(
            {
                "canonical_url": canonical_url(
                    request,
                    page_number=poems.number if not (query or collection or theme) else None,
                ),
                "poems": poems,
                "query": query,
                "seo_noindex": bool(query or collection or theme),
                "selected_collection": collection,
                "selected_theme": theme,
            }
        )
        return context


class PoemPage(Page):
    display_date = models.DateField(
        null=True,
        blank=True,
        help_text="Optional date shown to readers. Publication time is used otherwise.",
    )
    poem_body = models.TextField(
        help_text=(
            "Canonical poem text. Newlines, stanza gaps, Unicode, and leading spaces "
            "are preserved; HTML is always escaped."
        )
    )
    dedication = models.CharField(max_length=240, blank=True)
    epigraph = models.TextField(blank=True)
    epigraph_attribution = models.CharField(max_length=240, blank=True)
    notes = RichTextField(
        blank=True,
        features=["bold", "italic", "link"],
        help_text="Optional publication notes. Formatting is deliberately limited.",
    )
    collection = models.ForeignKey(
        Collection,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="poems",
    )
    themes = ClusterTaggableManager(through=PoemPageTag, blank=True)
    featured = models.BooleanField(default=False)
    listing_description = models.TextField(
        blank=True,
        max_length=320,
        help_text="A plain-text summary used in listings and feeds.",
    )
    social_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    parent_page_types = ["poems.PoemIndexPage"]
    subpage_types = []
    template = "poems/poem_page.html"

    content_panels = Page.content_panels + [
        FieldPanel("display_date"),
        FieldPanel("poem_body", widget=models.TextField().formfield().widget),
        FieldPanel("dedication"),
        MultiFieldPanel(
            [FieldPanel("epigraph"), FieldPanel("epigraph_attribution")],
            heading="Epigraph",
        ),
        FieldPanel("notes"),
        MultiFieldPanel(
            [
                FieldPanel("collection"),
                FieldPanel("themes"),
                FieldPanel("featured"),
            ],
            heading="Organization",
        ),
        MultiFieldPanel(
            [FieldPanel("listing_description"), FieldPanel("social_image")],
            heading="Listing and sharing",
        ),
    ]

    search_fields = Page.search_fields + [
        index.SearchField("poem_body"),
        index.SearchField("listing_description"),
        index.FilterField("featured"),
        index.RelatedFields("collection", [index.SearchField("name")]),
    ]

    @property
    def publication_date(self):
        if self.display_date:
            return self.display_date
        if self.first_published_at:
            return self.first_published_at.date()
        return None

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["previous_poem"], context["next_poem"] = self.get_public_neighbors()
        site_settings = PoetrySiteSettings.for_request(request)
        site_url = absolute_site_url(request)
        page_url = canonical_url(request)
        description = (
            self.search_description
            or self.listing_description
            or f"Read “{self.title},” a poem by {site_settings.author_name}."
        )
        structured_data = {
            "@context": "https://schema.org",
            "@type": "CreativeWork",
            "@id": f"{page_url}#poem",
            "url": page_url,
            "name": self.title,
            "description": description,
            "genre": "Poetry",
            "inLanguage": "en-US",
            "author": {"@id": f"{site_url}#author"},
            "isPartOf": {"@id": f"{site_url}#website"},
        }
        if self.publication_date:
            structured_data["datePublished"] = self.publication_date.isoformat()
        if self.last_published_at:
            structured_data["dateModified"] = self.last_published_at.isoformat()
        themes = list(self.themes.names())
        if themes:
            structured_data["keywords"] = themes

        context["canonical_url"] = page_url
        context["poem_meta_description"] = description
        context["poem_structured_data"] = serialize_json_ld(structured_data)
        return context

    def get_public_neighbors(self):
        ordered_ids = list(
            live_poems().sibling_of(self, inclusive=True).values_list("pk", flat=True)
        )
        try:
            position = ordered_ids.index(self.pk)
        except ValueError:
            return None, None

        previous_id = ordered_ids[position - 1] if position > 0 else None
        next_id = ordered_ids[position + 1] if position + 1 < len(ordered_ids) else None
        neighbor_ids = [pk for pk in (previous_id, next_id) if pk is not None]
        neighbors = PoemPage.objects.live().public().in_bulk(neighbor_ids)
        return neighbors.get(previous_id), neighbors.get(next_id)


class AboutPage(Page):
    body = RichTextField(
        blank=True,
        features=["h2", "h3", "bold", "italic", "link", "ol", "ul"],
    )

    max_count = 1
    parent_page_types = ["poems.HomePage"]
    subpage_types = []
    template = "poems/about_page.html"

    content_panels = Page.content_panels + [FieldPanel("body")]


def live_poems():
    return (
        PoemPage.objects.live()
        .public()
        .select_related("collection")
        .prefetch_related("themes")
        .alias(
            effective_publication_date=Coalesce(
                "display_date",
                Cast("first_published_at", output_field=models.DateField()),
                output_field=models.DateField(),
            )
        )
        .order_by(
            models.F("effective_publication_date").desc(nulls_last=True),
            models.F("first_published_at").desc(nulls_last=True),
            "-pk",
        )
    )


def public_collections():
    public_poem = live_poems().filter(collection_id=models.OuterRef("pk"))
    return Collection.objects.filter(models.Exists(public_poem)).order_by("name")


def public_themes():
    return (
        Tag.objects.filter(
            poems_poempagetag_items__content_object_id__in=live_poems().order_by().values("pk")
        )
        .distinct()
        .order_by("name")
    )
