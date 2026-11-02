from urllib.parse import urljoin
from django.db.models import ImageField
from django.utils import timezone
from .images import image_metadata


def public_settings(settings, request):
    data = {}
    for field in settings._meta.fields:
        if field.name in {"id", "updated_at", "llms_txt", "llms_full_txt", "control_labels"}:
            continue
        value = getattr(settings, field.name)
        if isinstance(field, ImageField):
            resolve = lambda url: urljoin(settings.site_url.rstrip("/") + "/", url) if settings.site_url else request.build_absolute_uri(url)
            media = image_metadata(value, resolve)
            data[field.name + "_media"] = media
            if value:
                value = media.get("compat_src", media["src"]) if field.name in {"favicon", "apple_touch_icon"} else media["src"]
            else:
                value = ""
        data[field.name] = value
    data['invoice_terms']=settings.invoice_terms.replace('{site_name}',settings.site_name)
    data["meta_title"] = settings.meta_title or settings.site_name
    data["og_title"] = settings.og_title or data["meta_title"]
    data["og_description"] = settings.og_description or settings.meta_description
    data["twitter_title"] = settings.twitter_title or data["og_title"]
    data["twitter_description"] = settings.twitter_description or data["og_description"]
    data["twitter_image"] = data["twitter_image"] or data["og_image"]
    data["twitter_image_alt"] = settings.twitter_image_alt or settings.og_image_alt
    data["footer_text"] = settings.footer_text or f"© {timezone.localdate().year} {settings.site_name}"
    return data
