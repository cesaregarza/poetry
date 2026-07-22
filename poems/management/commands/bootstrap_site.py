import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from wagtail.models import Page, Site

from poems.models import AboutPage, HomePage, PoemIndexPage, PoetrySiteSettings


class Command(BaseCommand):
    help = "Create or reconcile the initial poetry site tree and settings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hostname",
            default=os.environ.get("SITE_HOSTNAME", "poetry.cegarza.com"),
        )
        parser.add_argument("--port", type=int, default=None)

    @transaction.atomic
    def handle(self, *args, **options):
        hostname = options["hostname"]
        port = options["port"] or (80 if hostname == "localhost" else 443)
        root = Page.get_first_root_node()

        home = HomePage.objects.first()
        if home is None:
            existing = root.get_children().filter(slug="home").first()
            if existing:
                if (
                    existing.content_type.model != "page"
                    or existing.title != "Welcome to your new Wagtail site!"
                ):
                    raise CommandError(
                        "Cannot create HomePage: a non-starter page already uses "
                        "the root slug 'home'."
                    )
                Site.objects.filter(root_page=existing).delete()
                existing.delete()
                root.refresh_from_db()
            home = HomePage(title="Home", slug="home", show_in_menus=False)
            root.add_child(instance=home)
            home.save_revision().publish()

        poems = PoemIndexPage.objects.child_of(home).first()
        if poems is None:
            poems = PoemIndexPage(
                title="Poems",
                slug="poems",
                show_in_menus=True,
                intro="<p>Poems, gathered slowly.</p>",
            )
            home.add_child(instance=poems)
            poems.save_revision().publish()

        about = AboutPage.objects.child_of(home).first()
        if about is None:
            about = AboutPage(
                title="About",
                slug="about",
                show_in_menus=True,
                body="",
            )
            home.add_child(instance=about)
            about.save_revision().publish()

        Site.objects.exclude(hostname=hostname, port=port).update(is_default_site=False)
        site, _ = Site.objects.update_or_create(
            hostname=hostname,
            port=port,
            defaults={
                "site_name": "Cesar Garza — Poetry",
                "root_page": home,
                "is_default_site": True,
            },
        )
        PoetrySiteSettings.objects.get_or_create(site=site)

        self.stdout.write(
            self.style.SUCCESS(
                f"Poetry site ready at {hostname}:{port} (home={home.pk}, poems={poems.pk}, "
                f"about={about.pk})"
            )
        )
