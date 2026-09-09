"""Image header inspection and bounded display decoding."""

from __future__ import annotations

import warnings
from pathlib import Path
from threading import Event

from PIL import Image, ImageOps, UnidentifiedImageError

from mdhelper.core.workspace import ImageInfo, ImagePixels

from .text import check_cancel


def image_info(path: Path) -> ImageInfo | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                return ImageInfo(image.width, image.height, image.format or "Image")
    except UnidentifiedImageError:
        return None


def image_pixels(path: Path, size: tuple[int, int], cancel: Event | None) -> ImagePixels:
    if min(size) < 1:
        raise ValueError("Image viewport must have positive dimensions")
    check_cancel(cancel)
    bounds = (min(size[0], 2048), min(size[1], 2048))
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as source:
            source.draft("RGB", bounds)
            # Some decoders cannot downsample without materializing the source image.
            if source.width * source.height > 32 * 1024 * 1024:
                raise ValueError("Image decoder exceeds the memory limit at this resolution")
            source.thumbnail(bounds, Image.Resampling.LANCZOS)
            check_cancel(cancel)
            with ImageOps.exif_transpose(source) as oriented:
                oriented.thumbnail(bounds, Image.Resampling.LANCZOS)
                with oriented.convert("RGBA") as image:
                    return ImagePixels(image.width, image.height, image.tobytes())
