from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("poems", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="poempage",
            name="scansion_enabled",
            field=models.BooleanField(
                verbose_name="show stress assistant",
                default=False,
                help_text="Show the private stress assistant while editing this poem.",
            ),
        ),
        migrations.AddField(
            model_name="poempage",
            name="scansion_mode",
            field=models.CharField(
                verbose_name="guide",
                choices=[
                    ("general", "General stress"),
                    ("iambic_pentameter", "Iambic pentameter guide"),
                ],
                default="general",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="poempage",
            name="scansion_overrides",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
