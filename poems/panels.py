from django.urls import reverse
from wagtail.admin.panels import Panel

from poems.seo import poem_instagram_card_url, poem_social_card_url
from poems.social_cards import InstagramCardTooLong, instagram_carousel_layouts


class SocialPreviewPanel(Panel):
    class BoundPanel(Panel.BoundPanel):
        template_name = "poems/admin/social_preview_panel.html"

        def get_context_data(self, parent_context=None):
            context = super().get_context_data(parent_context)
            if not self.instance or not self.instance.pk:
                context["is_saved"] = False
                return context

            context["is_saved"] = True
            page_id = self.instance.pk
            context["open_graph_preview_url"] = reverse(
                "admin_poem_social_card_preview",
                kwargs={"page_id": page_id},
            )
            context["instagram_preview_url"] = reverse(
                "admin_poem_instagram_card_preview",
                kwargs={"page_id": page_id},
            )

            if self.instance.social_image_id:
                rendition = self.instance.social_image.get_rendition("fill-1200x630")
                context["open_graph_preview_url"] = rendition.url
                context["open_graph_uses_upload"] = True

            try:
                layouts = instagram_carousel_layouts(
                    self.instance.title,
                    self.instance.poem_body,
                    self.instance.dedication,
                )
            except InstagramCardTooLong as error:
                context["instagram_error"] = str(error)
            else:
                if len(layouts) > 1:
                    context["instagram_slide_count"] = len(layouts)
                    context["instagram_slides"] = [
                        {
                            "number": number,
                            "url": reverse(
                                "admin_poem_instagram_carousel_slide",
                                kwargs={"page_id": page_id, "slide_number": number},
                            ),
                        }
                        for number in range(1, len(layouts) + 1)
                    ]
                    context["instagram_carousel_download_url"] = reverse(
                        "admin_poem_instagram_carousel_download",
                        kwargs={"page_id": page_id},
                    )

            live_poem = self.panel.model.objects.live().public().filter(pk=page_id).first()
            if live_poem:
                from poems.models import PoetrySiteSettings

                site_settings = PoetrySiteSettings.for_request(self.request)
                if live_poem.social_image_id:
                    rendition = live_poem.social_image.get_rendition("fill-1200x630")
                    context["public_open_graph_url"] = self.request.build_absolute_uri(
                        rendition.url
                    )
                else:
                    context["public_open_graph_url"] = poem_social_card_url(
                        self.request,
                        live_poem,
                        site_settings,
                    )
                context["public_instagram_url"] = poem_instagram_card_url(
                    self.request,
                    live_poem,
                )

            return context


class ScansionPanel(Panel):
    class BoundPanel(Panel.BoundPanel):
        template_name = "poems/admin/scansion_panel.html"

        def get_context_data(self, parent_context=None):
            context = super().get_context_data(parent_context)
            context["scansion_analysis_url"] = reverse("admin_poem_scansion_analysis")
            context["scansion_page_id"] = self.instance.pk if self.instance else None
            return context
