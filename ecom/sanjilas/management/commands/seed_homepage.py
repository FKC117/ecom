"""Non-destructive, optional preview content for the local storefront."""
from django.core.management.base import BaseCommand
from django.db import transaction
from sanjilas.models import SiteSettings, HomePage, Collection, Product


class Command(BaseCommand):
    help = "Create editable preview homepage content; never overwrite existing records."

    @transaction.atomic
    def handle(self, *args, **options):
        SiteSettings.objects.get_or_create(pk=1)
        HomePage.objects.get_or_create(pk=1, defaults={
            "hero_image": "homepage/preview/hero.jpg",
            "story_image": "homepage/preview/story.jpg",
        })
        rows = [
            ("Rings", "rings", "Small circles. Endless possibilities.", "The Solstice Ring", "A little golden hour", "A sculptural ring with a softly rounded silhouette. An example piece from our preview edit.", "The preview edit"),
            ("Necklaces", "necklaces", "Keep something beautiful close.", "The Everyday Pendant", "Your new signature", "A delicate pendant with a warm, understated presence. An example piece from our preview edit.", ""),
            ("Earrings", "earrings", "A frame for your favourite moments.", "The Golden Hour Hoops", "An effortless finishing touch", "An easy pair of hoops, imagined for your everyday jewellery box. An example piece from our preview edit.", "The preview edit"),
            ("Bracelets", "bracelets", "A little joy, within arm’s reach.", "The Quiet Statement", "Considered in every detail", "A simple bracelet that makes room for your own way of wearing it. An example piece from our preview edit.", ""),
        ]
        for position, (name, slug, description, product_name, subtitle, body, badge) in enumerate(rows):
            collection, _ = Collection.objects.get_or_create(slug=slug, defaults={
                "name": name, "description": description, "position": position,
                "image": f"homepage/preview/{slug}.jpg", "image_alt": f"A closer look at {name.lower()}",
            })
            Product.objects.get_or_create(slug=slug + "-preview", defaults={
                "name": product_name, "collection": collection, "subtitle": subtitle,
                "description": body, "badge": badge, "position": position,
                "image": f"homepage/preview/{slug}.jpg", "image_alt": f"Jewellery inspiration for {name.lower()}",
            })
        self.stdout.write(self.style.SUCCESS("Editable preview content ready. Existing content was preserved."))
