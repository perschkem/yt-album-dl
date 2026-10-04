"""Cover: eigenes Bild per URL laden, prüfen, zwischenspeichern – und Bilder für das Einbetten aufbereiten."""

from __future__ import annotations

import hashlib
import io
import urllib.request
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .i18n import t

COVER_SIZE = 1000
MAX_BYTES = 10 * 1024 * 1024
TIMEOUT = 15
_HEADERS = {"User-Agent": "Mozilla/5.0 (yt-album-dl)"}


class CoverError(ValueError):
    """Cover-URL lässt sich nicht als Bild verwenden – Meldung ist für die Oberfläche gedacht."""


def _download(url: str) -> bytes:
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise CoverError(t("errors.cover_scheme"))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_HEADERS), timeout=TIMEOUT) as res:
            data = res.read(MAX_BYTES + 1)
    except Exception as exc:
        raise CoverError(t("errors.cover_download", error=exc)) from exc
    if len(data) > MAX_BYTES:
        raise CoverError(t("errors.cover_too_large"))
    return data


def _open(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise CoverError(t("errors.cover_not_image")) from exc
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


# ---------- Bilder aufbereiten ----------

BAR_LUMA = 28  # Pixel dunkler als das gelten als „schwarz“ (JPEG-Rauschen toleriert)
BAR_SHARE = 0.97  # so viel Anteil einer Zeile/Spalte muss dunkel sein
BAR_MAX = 0.45  # höchstens so viel pro Seite abschneiden


def trim_bars(img: Image.Image) -> Image.Image:
    """Schneidet schwarze Balken ab (links/rechts bei quadratischem Cover im 16:9-Vorschaubild, oben/unten bei
    Letterbox). Einfarbig dunkle Bilder bleiben unverändert."""
    gray = img.convert("L")
    w, h = gray.size
    px = gray.load()

    def dark_col(x: int) -> bool:
        return sum(px[x, y] < BAR_LUMA for y in range(0, h, 2)) >= BAR_SHARE * len(range(0, h, 2))

    def dark_row(y: int) -> bool:
        return sum(px[x, y] < BAR_LUMA for x in range(0, w, 2)) >= BAR_SHARE * len(range(0, w, 2))

    left = 0
    while left < w * BAR_MAX and dark_col(left):
        left += 1
    right = w
    while w - right < w * BAR_MAX and dark_col(right - 1):
        right -= 1
    top = 0
    while top < h * BAR_MAX and dark_row(top):
        top += 1
    bottom = h
    while h - bottom < h * BAR_MAX and dark_row(bottom - 1):
        bottom -= 1
    if right - left < w * 0.2 or bottom - top < h * 0.2:  # fast alles dunkel → nichts abschneiden
        return img
    return img.crop((left, top, right, bottom)) if (left, top, right, bottom) != (0, 0, w, h) else img


def center_square(img: Image.Image) -> Image.Image:
    """Mittig quadratisch zuschneiden."""
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    return img.crop((left, top, left + side, top + side))


def to_jpeg(img: Image.Image, size: int, quality: int, crop: bool = True) -> bytes:
    """JPEG-Bytes, höchstens size × size px. crop=True entfernt schwarze Balken und schneidet mittig quadratisch zu
    (für YouTube-Vorschaubilder, die 16:9 sind)."""
    img = img.convert("RGB")
    if crop:
        img = center_square(trim_bars(img))  # erst schwarze Ränder weg, dann mittig quadratisch
    img.thumbnail((size, size), Image.LANCZOS)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def cover_jpeg(image_path: Path, crop: bool = True) -> bytes:
    """Cover zum Einbetten, max. COVER_SIZE px; eigene Cover bleiben auf Wunsch unbeschnitten (crop=False)."""
    with Image.open(image_path) as img:
        return to_jpeg(img, COVER_SIZE, quality=90, crop=crop)


def thumbnail_preview(url: str, size: int = 300) -> bytes:
    """Vorschaubild so, wie es als Cover eingebettet würde: schwarze Balken weg, mittig quadratisch."""
    return to_jpeg(_open(_download(url)), size, quality=88)
