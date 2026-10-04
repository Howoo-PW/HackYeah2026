"""Segment photos: image validation, EXIF removal, thumbnails and the private Supabase Storage bucket."""

from dataclasses import dataclass
from io import BytesIO
from uuid import uuid4

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from .config import settings
from .errors import AppError

BUCKET = "segment-photos"
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000
THUMBNAIL_SIDE = 400
SIGNED_URL_SECONDS = 3600
# format reported by Pillow -> (content type, file extension)
FORMATS = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp")}


@dataclass
class ProcessedImage:
    """A clean copy of an upload and its thumbnail, ready for storage."""

    full: bytes
    thumbnail: bytes
    content_type: str
    extension: str


def process_image(data: bytes) -> ProcessedImage:
    """Validate that `data` is a JPEG, PNG or WebP picture and return it re-encoded without metadata, plus a thumbnail.

    Re-encoding drops EXIF (including GPS) and any data appended to the file; the orientation from EXIF is applied first.
    """
    if len(data) > MAX_BYTES:
        raise AppError(413, "FILE_TOO_LARGE", "Zdjęcie jest większe niż 5 MB")
    try:
        with Image.open(BytesIO(data)) as probe:
            image_format = probe.format
            if image_format not in FORMATS:
                raise AppError(415, "UNSUPPORTED_MEDIA_TYPE", "Dozwolone są pliki JPEG, PNG i WebP")
            if probe.width * probe.height > MAX_PIXELS:
                raise AppError(413, "FILE_TOO_LARGE", "Zdjęcie ma zbyt dużą rozdzielczość")
            image = ImageOps.exif_transpose(probe)
            image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise AppError(415, "UNSUPPORTED_MEDIA_TYPE", "Dozwolone są pliki JPEG, PNG i WebP") from None

    content_type, extension = FORMATS[image_format]
    if image.mode == "P":
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
    elif image_format == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    clean = Image.new(image.mode, image.size)  # a fresh image carries no EXIF, ICC profile or trailing data
    clean.paste(image)
    full = BytesIO()
    save_options = {"quality": 88} if image_format in ("JPEG", "WEBP") else {}
    clean.save(full, format=image_format, **save_options)

    thumb = clean.convert("RGB") if clean.mode not in ("RGB", "L") else clean
    thumb.thumbnail((THUMBNAIL_SIDE, THUMBNAIL_SIDE))
    thumbnail = BytesIO()
    thumb.save(thumbnail, format="JPEG", quality=80)
    return ProcessedImage(full.getvalue(), thumbnail.getvalue(), content_type, extension)


def new_paths(segment_id: int, extension: str) -> tuple[str, str]:
    """Object paths for a new photo and its thumbnail, grouped by segment."""
    name = uuid4()
    return f"{segment_id}/{name}.{extension}", f"{segment_id}/{name}_thumb.jpg"


def _storage() -> tuple[str, dict[str, str]]:
    """Storage API base URL and the service key headers; the key never leaves the backend."""
    key = settings.supabase_service_role_key.get_secret_value()
    if not settings.supabase_url or not key:
        raise AppError(503, "STORAGE_UNAVAILABLE", "Zdjęcia są chwilowo niedostępne")
    headers = {"apikey": key}
    # New secret keys are API keys, not JWTs; legacy service_role keys are both.
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return f"{settings.supabase_url.rstrip('/')}/storage/v1", headers


def upload(path: str, data: bytes, content_type: str) -> None:
    """Store one object in the private bucket."""
    base, headers = _storage()
    try:
        response = httpx.post(f"{base}/object/{BUCKET}/{path}", content=data, timeout=20,
                              headers={**headers, "Content-Type": content_type, "x-upsert": "false"})
    except httpx.HTTPError:
        raise AppError(503, "STORAGE_UNAVAILABLE", "Zdjęcia są chwilowo niedostępne") from None
    if response.status_code not in (200, 201):
        raise AppError(503, "STORAGE_UNAVAILABLE", "Nie udało się zapisać zdjęcia")


def remove(paths: list[str]) -> None:
    """Best-effort cleanup of objects, e.g. after a failed database insert."""
    try:
        base, headers = _storage()
        httpx.request("DELETE", f"{base}/object/{BUCKET}", json={"prefixes": paths}, headers=headers, timeout=10)
    except (AppError, httpx.HTTPError):
        pass


def sign(paths: list[str]) -> dict[str, str]:
    """Signed URLs (valid one hour) for the given object paths; a path that cannot be signed is left out."""
    if not paths:
        return {}
    base, headers = _storage()
    try:
        response = httpx.post(f"{base}/object/sign/{BUCKET}", json={"expiresIn": SIGNED_URL_SECONDS, "paths": paths},
                              headers=headers, timeout=10)
        response.raise_for_status()
        rows = response.json()
    except (httpx.HTTPError, ValueError):
        raise AppError(503, "STORAGE_UNAVAILABLE", "Zdjęcia są chwilowo niedostępne") from None
    return {row["path"]: f"{base}{row['signedURL']}" for row in rows if row.get("signedURL")}


def with_urls(rows: list[dict]) -> list[dict]:
    """Rows from `segment_photos` with signed `url` and `thumbnail_url` instead of the storage paths."""
    urls = sign([p for row in rows for p in (row["storage_path"], row["thumbnail_path"])])
    return [{"id": row["id"], "segment_id": row["segment_id"], "taken_at": row["taken_at"], "created_at": row["created_at"],
             "status": row["status"], "url": urls.get(row["storage_path"], ""),
             "thumbnail_url": urls.get(row["thumbnail_path"], "")} for row in rows]

