"""Bounded still-image validation. Analysis retains original bytes in memory only."""

import warnings
from dataclasses import dataclass
from io import BytesIO

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import Settings
from app.core.errors import ServiceError

FORMATS = {
    "image/jpeg": ("JPEG", "jpg"),
    "image/png": ("PNG", "png"),
    "image/webp": ("WEBP", "webp"),
}


@dataclass(frozen=True)
class ImageData:
    data: bytes
    content_type: str
    extension: str
    width: int
    height: int


def validate_image(data: bytes, declared_mime: str, settings: Settings) -> ImageData:
    if declared_mime not in FORMATS:
        raise ServiceError("UNSUPPORTED_FORMAT", "Choose a JPEG, PNG, or WebP image.", 415)
    if not data:
        raise ServiceError("INVALID_IMAGE", "The image is empty or missing.", 400)
    if len(data) > settings.max_image_bytes:
        raise ServiceError("IMAGE_TOO_LARGE", "Each image must be no larger than 10 MiB.", 413)
    expected, extension = FORMATS[declared_mime]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != expected:
                    raise ServiceError("INVALID_IMAGE", "Image bytes do not match the declared file type.", 400)
                width, height = image.size
                if width * height > settings.max_image_pixels:
                    raise ServiceError("EXCESSIVE_DIMENSIONS", "Use an image with at most 20 megapixels.", 413)
                if getattr(image, "n_frames", 1) != 1 or bool(image.info.get("duration")):
                    raise ServiceError("INVALID_IMAGE", "Animated images are not supported.", 400)
                image.verify()
            with Image.open(BytesIO(data)) as decoded:
                decoded.load()
    except ServiceError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ServiceError("INVALID_IMAGE", "The image is damaged or could not be decoded.", 400) from exc
    return ImageData(data, declared_mime, extension, width, height)


async def read_upload(upload: UploadFile | None, role: str, settings: Settings) -> ImageData:
    if upload is None:
        raise ServiceError("MISSING_IMAGE", f"The {role} image is required.", 400)
    data = await upload.read(settings.max_image_bytes + 1)
    return validate_image(data, upload.content_type or "", settings)
