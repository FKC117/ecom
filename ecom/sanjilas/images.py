"""One raster-image processing pipeline; storage is handled by WebPImageField."""
import io
import json
import math
import re
import uuid
import warnings
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageCms, ImageEnhance, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener(thumbnails=False)
VARIANT_WIDTHS = (320, 640, 960, 1280, 1600)  # Immutable webp1 filename policy.
FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "TIFF", "BMP", "ICO", "AVIF", "HEIF"}
ACCEPT = ".jpg,.jpeg,.png,.webp,.gif,.tif,.tiff,.bmp,.ico,.avif,.heic,.heif"
NAME = re.compile(r"^(webp1|icon1)_[0-9a-f]{32}_(\d+)x(\d+)\.webp$")
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))


def limits():
    return {
        "max_bytes": getattr(settings, "IMAGE_MAX_UPLOAD_BYTES", 15 * 1024 * 1024),
        "max_pixels": getattr(settings, "IMAGE_MAX_PIXELS", 32_000_000),
        "max_edge": getattr(settings, "IMAGE_MAX_EDGE", 2560),
    }


def parse_edits(value):
    if value is None or value == "":
        return {}
    try:
        edits = json.loads(value) if isinstance(value, str) else value
        allowed = {"crop", "rotate", "flip_horizontal", "flip_vertical", "brightness", "contrast", "resize_width"}
        if not isinstance(edits, dict) or edits.keys() - allowed:
            raise ValueError
        for key in ("flip_horizontal", "flip_vertical"):
            if key in edits and not isinstance(edits[key], bool):
                raise ValueError
        if type(edits.get("rotate", 0)) is not int or edits.get("rotate", 0) not in (0, 90, 180, 270):
            raise ValueError
        for key in ("brightness", "contrast"):
            number = edits.get(key, 1)
            if type(number) not in (float, int) or not math.isfinite(number) or not .5 <= number <= 1.5:
                raise ValueError
        width = edits.get("resize_width", 0)
        if type(width) is not int or (width != 0 and not 32 <= width <= limits()["max_edge"]):
            raise ValueError
        if "crop" in edits:
            crop = edits["crop"]
            if not isinstance(crop, dict) or set(crop) != {"x", "y", "width", "height"}:
                raise ValueError
            if any(type(n) not in (float, int) or not math.isfinite(n) for n in crop.values()):
                raise ValueError
            if not (0 <= crop["x"] < 1 and 0 <= crop["y"] < 1 and 0 < crop["width"] <= 1 and 0 < crop["height"] <= 1):
                raise ValueError
            if crop["x"] + crop["width"] > 1.000001 or crop["y"] + crop["height"] > 1.000001:
                raise ValueError
        return edits
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ValidationError("Invalid image edits. Keep the crop inside the image and use the supported adjustment ranges.")


def _read(source):
    maximum = limits()["max_bytes"]
    if getattr(source, "size", 0) > maximum:
        raise ValidationError(f"The image must be no larger than {maximum // (1024 * 1024)} MB.")
    opened_here = getattr(source, "closed", False)
    if opened_here:
        source.open("rb")
    try:
        source.seek(0)
        data = source.read(maximum + 1)
        source.seek(0)
    finally:
        if opened_here:
            source.close()
    if len(data) > maximum:
        raise ValidationError(f"The image must be no larger than {maximum // (1024 * 1024)} MB.")
    return data


def _colour(image):
    alpha = "A" in image.getbands() or "transparency" in image.info
    mode = "RGBA" if alpha else "RGB"
    profile = image.info.get("icc_profile")
    if profile:
        try:
            return ImageCms.profileToProfile(image, ImageCms.ImageCmsProfile(io.BytesIO(profile)), SRGB, outputMode=mode)
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass
    return image.convert(mode)


def _webp(image, quality):
    data = io.BytesIO()
    image.save(data, "WEBP", quality=quality, method=6, exact=True, icc_profile=SRGB.tobytes())
    return data.getvalue()


class ProcessedImage(ContentFile):
    def __init__(self, image, *, icon_size=0, variants=True):
        self.width, self.height = image.size
        self.icon_size = icon_size
        self.derivatives = {}
        if variants and not icon_size:
            for width in VARIANT_WIDTHS:
                if width < image.width:
                    smaller = image.resize((width, max(1, round(image.height * width / image.width))), Image.Resampling.LANCZOS)
                    self.derivatives[f"_{width}w.webp"] = _webp(smaller, getattr(settings, "IMAGE_WEBP_VARIANT_QUALITY", 84))
        if icon_size:
            png = io.BytesIO()
            image.save(png, "PNG", optimize=True, icc_profile=SRGB.tobytes())
            self.derivatives["_compat.png"] = png.getvalue()
        name = f"{'icon1' if icon_size else 'webp1'}_{uuid.uuid4().hex}_{image.width}x{image.height}.webp"
        super().__init__(_webp(image, getattr(settings, "IMAGE_WEBP_QUALITY", 90)), name=name)


def prepare_image(source, edits=None, *, icon_size=0, variants=True):
    edits = parse_edits(edits)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(_read(source))) as original:
                if original.format not in FORMATS:
                    raise ValidationError("Unsupported image format. Upload JPEG, PNG, WebP, GIF, TIFF, BMP, ICO, AVIF, HEIC or HEIF.")
                if original.width * original.height > limits()["max_pixels"] or max(original.size) > 16000:
                    raise ValidationError("The image dimensions are too large. Upload an image below 32 megapixels and 16,000 pixels per side.")
                # Animated/multi-page uploads deliberately use their first frame.
                original.seek(0)
                image = _colour(ImageOps.exif_transpose(original))
        if edits.get("rotate"):
            image = image.rotate(-edits["rotate"], expand=True)
        if edits.get("flip_horizontal"):
            image = ImageOps.mirror(image)
        if edits.get("flip_vertical"):
            image = ImageOps.flip(image)
        if crop := edits.get("crop"):
            left, top = round(crop["x"] * image.width), round(crop["y"] * image.height)
            right = min(image.width, round((crop["x"] + crop["width"]) * image.width))
            bottom = min(image.height, round((crop["y"] + crop["height"]) * image.height))
            if right <= left or bottom <= top:
                raise ValidationError("The selected crop is too small.")
            image = image.crop((left, top, right, bottom))
        alpha = image.getchannel("A") if image.mode == "RGBA" else None
        if alpha is not None:
            image = image.convert("RGB")
        image = ImageEnhance.Brightness(image).enhance(edits.get("brightness", 1))
        image = ImageEnhance.Contrast(image).enhance(edits.get("contrast", 1))
        if alpha is not None:
            image.putalpha(alpha)
        maximum = icon_size or limits()["max_edge"]
        image.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
        if (width := edits.get("resize_width", 0)) and width < image.width:
            image = image.resize((width, max(1, round(image.height * width / image.width))), Image.Resampling.LANCZOS)
        return ProcessedImage(image, icon_size=icon_size, variants=variants)
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValidationError("The image could not be decoded safely. Upload a valid supported image.") from error


def derivative_name(name, suffix):
    return str(PurePosixPath(name).with_suffix("")) + suffix


def image_metadata(value, resolve_url=None):
    if not value:
        return None
    resolve_url = resolve_url or (lambda url: url)
    result = {"src": resolve_url(value.url), "width": None, "height": None, "srcset": ""}
    match = NAME.match(PurePosixPath(value.name).name)
    if not match:
        return result
    policy, width, height = match.groups()
    width, height = int(width), int(height)
    result.update(width=width, height=height)
    if policy == "webp1":
        sizes = [(resolve_url(value.storage.url(derivative_name(value.name, f"_{size}w.webp"))), size) for size in VARIANT_WIDTHS if size < width]
        result["srcset"] = ", ".join(f"{url} {size}w" for url, size in [*sizes, (result["src"], width)])
    else:
        result["compat_src"] = resolve_url(value.storage.url(derivative_name(value.name, "_compat.png")))
    return result
