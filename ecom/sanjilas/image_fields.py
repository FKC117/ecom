from dataclasses import dataclass
import json

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.db.models.fields.files import ImageFieldFile
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from .images import ACCEPT, ProcessedImage, derivative_name, parse_edits, prepare_image


@dataclass
class ImageInput:
    upload: object
    edits: object = None


class WebPImageInput(forms.ClearableFileInput):
    def value_from_datadict(self, data, files, name):
        edits = data.get(name + "__edits", "")
        if not edits and data.get(name + "__enable_edits"):
            try:
                edits = json.dumps({
                    "rotate": int(data.get(name + "__rotate", 0)),
                    "flip_horizontal": bool(data.get(name + "__flip_horizontal")),
                    "flip_vertical": bool(data.get(name + "__flip_vertical")),
                    "brightness": float(data.get(name + "__brightness", 1)),
                    "contrast": float(data.get(name + "__contrast", 1)),
                    "resize_width": int(data.get(name + "__resize_width", 0)),
                    "crop": {key: float(data.get(name + "__crop_" + key, default)) / 100 for key, default in (("x", 0), ("y", 0), ("width", 100), ("height", 100))},
                })
            except (ValueError, TypeError):
                edits = "invalid"
        return ImageInput(super().value_from_datadict(data, files, name), edits)

    def render(self, name, value, attrs=None, renderer=None):
        from .control_copy import control_labels
        from .images import limits
        from .models import SiteSettings
        standard = super().render(name, value, attrs, renderer)
        copy = {**control_labels(), **SiteSettings.load().control_labels}
        editor = render_to_string("sanjilas/widgets/image_edits.html", {"name": name, "value": value, "copy": copy, "max_edge": limits()["max_edge"]})
        return mark_safe(str(standard) + editor)


class WebPImageFormField(forms.ImageField):
    def __init__(self, *args, icon_size=0, **kwargs):
        widget = kwargs.pop("widget", None)
        attrs = widget.attrs if isinstance(widget, forms.Widget) else {}
        kwargs["widget"] = WebPImageInput(attrs={**attrs, "accept": ACCEPT})
        self.icon_size = icon_size
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not isinstance(data, ImageInput):
            data = ImageInput(data)
        edits = parse_edits(data.edits)
        upload = data.upload
        if upload is False and edits:
            raise ValidationError("Choose either image removal or editing, not both.")
        if upload is False or upload is forms.widgets.FILE_INPUT_CONTRADICTION:
            return super().clean(upload, initial)
        if upload or edits:
            source = upload or initial
            if not source:
                raise ValidationError("Upload an image before editing it.")
            prepared = prepare_image(source, edits, icon_size=self.icon_size)
            return super().clean(prepared, initial)
        return super().clean(None, initial)

    def has_changed(self, initial, data):
        if isinstance(data, ImageInput):
            return bool(data.edits) or super().has_changed(initial, data.upload)
        return super().has_changed(initial, data)


class WebPImageFile(ImageFieldFile):
    def save(self, name, content, save=True):
        prepared = content if isinstance(content, ProcessedImage) else prepare_image(content, icon_size=self.field.icon_size)
        previous_name = self.name
        created = []
        try:
            super().save(prepared.name, prepared, save=False)
            created.append(self.name)
            for suffix, data in prepared.derivatives.items():
                created.append(self.storage.save(derivative_name(self.name, suffix), ContentFile(data)))
        except Exception:
            # Only files created by this operation are eligible for cleanup.
            for created_name in created:
                self.storage.delete(created_name)
            self.name = previous_name
            setattr(self.instance, self.field.attname, previous_name)
            raise
        if save:
            self.instance.save()


class WebPImageField(models.ImageField):
    attr_class = WebPImageFile

    def __init__(self, *args, icon_size=0, **kwargs):
        self.icon_size = icon_size
        kwargs.setdefault("max_length", 255)
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        return super().formfield(**{"form_class": WebPImageFormField, "icon_size": self.icon_size, **kwargs})

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.icon_size:
            kwargs["icon_size"] = self.icon_size
        return name, path, args, kwargs
