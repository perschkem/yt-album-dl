"""Eigenes Cover per URL: laden, prüfen, zwischenspeichern."""

from __future__ import annotations

import hashlib
import io
import urllib.request
from pathlib import Path

from PIL import Image, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
TIMEOUT = 15
_HEADERS = {"User-Agent": "Mozilla/5.0 (yt-album-dl)"}


class CoverError(ValueError):
    """Cover-URL lässt sich nicht als Bild verwenden – Meldung ist für die Oberfläche gedacht."""


def _download(url: str) -> bytes:
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise CoverError("Die Cover-URL muss mit http:// oder https:// beginnen")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_HEADERS), timeout=TIMEOUT) as res:
            data = res.read(MAX_BYTES + 1)
    except Exception as exc:
        raise CoverError(f"Cover konnte nicht geladen werden: {exc}") from exc
    if len(data) > MAX_BYTES:
        raise CoverError("Das Cover ist größer als 10 MB")
    return data


def _open(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise CoverError("Unter der URL liegt kein Bild (z.B. eine Webseite statt der Bilddatei)") from exc
    return img


def check_cover(url: str) -> dict:
    """Prüft eine Cover-URL für die Vorschau in der Oberfläche."""
    img = _open(_download(url))
    return {"width": img.width, "height": img.height, "format": img.format, "square": img.width == img.height}


def fetch_cover(url: str, cache_dir: Path) -> Path:
    """Lädt das Cover (einmal pro URL) und legt es als JPEG im Zwischenspeicher ab."""
    target = cache_dir / f"{hashlib.sha1(url.strip().encode()).hexdigest()}.jpg"
    if target.exists():
        return target
    img = _open(_download(url)).convert("RGB")
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    img.save(tmp, format="JPEG", quality=92)
    tmp.replace(target)
    return target


def thumbnail_preview(url: str, size: int = 300) -> bytes:
    """Vorschaubild so, wie es als Cover eingebettet würde: schwarze Balken weg, mittig quadratisch."""
    from .tagger import trim_bars  # hier importiert, um Kreisimporte zu vermeiden

    img = trim_bars(_open(_download(url)).convert("RGB"))
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side))
    img.thumbnail((size, size), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()
