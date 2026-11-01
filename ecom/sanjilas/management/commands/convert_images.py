from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from sanjilas.image_fields import WebPImageField
from sanjilas.images import NAME, prepare_image
from pathlib import PurePosixPath


class Command(BaseCommand):
    help = "Preview or convert existing image fields to the WebP engine. Original files are retained."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        count = 0
        for model in apps.get_app_config("sanjilas").get_models():
            fields = [field for field in model._meta.fields if isinstance(field, WebPImageField)]
            if not fields:
                continue
            for obj in model.objects.iterator():
                for field in fields:
                    current = getattr(obj, field.name)
                    if not current or NAME.match(PurePosixPath(current.name).name):
                        continue
                    self.stdout.write(f"{model._meta.label} #{obj.pk}: {field.name} ({current.name})")
                    count += 1
                    try:
                        prepared = prepare_image(current, icon_size=field.icon_size)
                        self.stdout.write(f"  {current.size:,} bytes -> {prepared.size:,} byte WebP master; {len(prepared.derivatives)} derivative files")
                        if options["apply"]:
                            with transaction.atomic():
                                setattr(obj, field.name, prepared)
                                # Model.save avoids rewriting unrelated settings/content columns.
                                obj.save(update_fields=[field.name])
                    except Exception as error:
                        raise CommandError(f"Image conversion failed for {model._meta.label} #{obj.pk} / {field.name}: {error}") from error
        self.stdout.write(self.style.SUCCESS(f"{count} image fields {'converted' if options['apply'] else 'would be converted (dry run)'}. Original files retained."))
