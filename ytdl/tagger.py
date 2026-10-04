"""Tags und Cover schreiben: ID3 für MP3, MP4-Atome für M4A."""

from __future__ import annotations

import io
from pathlib import Path

from mutagen.id3 import APIC, COMM, ID3, TALB, TCMP, TCON, TDRC, TIT2, TPE1, TPE2, TRCK, WOAS
from mutagen.mp4 import MP4, MP4Cover
from PIL import Image

from .metadata import MUSIK, Item

COVER_SIZE = 1000
VARIOUS_ARTISTS = "Various Artists"


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


def cover_jpeg(image_path: Path, crop: bool = True) -> bytes:
    """Cover als JPEG-Bytes, max. COVER_SIZE px. crop=True entfernt schwarze Balken und schneidet mittig
    quadratisch zu (für YouTube-Vorschaubilder, die 16:9 sind); eigene Cover bleiben auf Wunsch unbeschnitten."""
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        if crop:
            img = trim_bars(img)  # erst schwarze Ränder weg, dann mittig quadratisch
            side = min(img.size)
            left = (img.width - side) // 2
            top = (img.height - side) // 2
            img = img.crop((left, top, left + side, top + side))
        img.thumbnail((COVER_SIZE, COVER_SIZE), Image.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()


square_cover = cover_jpeg  # alter Name


def _date(item: Item) -> str:
    return item.date if item.mode != MUSIK and item.date else item.year


def _comment(item: Item) -> str:
    return item.description if item.mode != MUSIK and item.description else item.url


def write_tags(path: Path, item: Item, cover: Path | None = None, crop: bool = True) -> None:
    if path.suffix.lower() == ".m4a":
        _write_mp4(path, item, cover, crop)
    else:
        _write_id3(path, item, cover, crop)


def _write_mp4(path: Path, item: Item, cover: Path | None, crop: bool) -> None:
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    tags.clear()
    tags["\xa9nam"] = [item.title]
    tags["\xa9ART"] = [item.artist]
    tags["aART"] = [item.album_artist or item.artist]
    if item.album:
        tags["\xa9alb"] = [item.album]
    if item.album_artist == VARIOUS_ARTISTS:
        tags["cpil"] = True
    if item.track_no:
        tags["trkn"] = [(item.track_no, item.track_total or 0)]
    if date := _date(item):
        tags["\xa9day"] = [date]
    if item.genre:
        tags["\xa9gen"] = [item.genre]
    if comment := _comment(item):
        tags["\xa9cmt"] = [comment]
    if cover and cover.exists():
        tags["covr"] = [MP4Cover(cover_jpeg(cover, crop), imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


def _write_id3(mp3: Path, item: Item, cover: Path | None, crop: bool) -> None:
    tags = ID3()
    tags.add(TIT2(encoding=3, text=item.title))
    tags.add(TPE1(encoding=3, text=item.artist))
    tags.add(TPE2(encoding=3, text=item.album_artist or item.artist))
    if item.album:
        tags.add(TALB(encoding=3, text=item.album))
    if item.album_artist == VARIOUS_ARTISTS:
        tags.add(TCMP(encoding=3, text="1"))  # Sampler/Compilation – Player gruppieren das Album dann richtig
    if item.track_no:
        track = f"{item.track_no}/{item.track_total}" if item.track_total else str(item.track_no)
        tags.add(TRCK(encoding=3, text=track))
    if date := _date(item):
        tags.add(TDRC(encoding=3, text=date))
    if item.genre:
        tags.add(TCON(encoding=3, text=item.genre))
    if item.url:
        tags.add(WOAS(url=item.url))
    if comment := _comment(item):
        tags.add(COMM(encoding=3, lang="deu", desc="", text=comment))
    if cover and cover.exists():
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_jpeg(cover, crop)))
    tags.save(mp3, v2_version=4)
