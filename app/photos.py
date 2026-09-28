"""Photo storage: uploads are re-encoded as JPEG (EXIF stripped, max 1800px) into UPLOAD_DIR/<listing_id>/."""
from __future__ import annotations

import io
import os
import secrets

from PIL import Image, ImageOps, UnidentifiedImageError

from . import settings

MAX_EDGE = 1800


class PhotoError(ValueError):
    pass


def save_upload(listing_id: int, data: bytes) -> str:
    """Returns the public URL path (/uploads/<listing>/<name>.jpg)."""
    if len(data) > settings.MAX_PHOTO_BYTES:
        raise PhotoError("Photo is too large (max 12 MB).")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise PhotoError("That file is not an image.") from e
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    folder = os.path.join(settings.UPLOAD_DIR, str(listing_id))
    os.makedirs(folder, exist_ok=True)
    name = f"{secrets.token_hex(8)}.jpg"
    img.save(os.path.join(folder, name), "JPEG", quality=85, optimize=True, progressive=True)
    return f"/uploads/{listing_id}/{name}"


def delete_file(url: str) -> None:
    if not url.startswith("/uploads/"):
        return
    path = os.path.join(settings.UPLOAD_DIR, *url[len("/uploads/"):].split("/"))
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
