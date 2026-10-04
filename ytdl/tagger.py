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


def square_cover(image_path: Path) -> bytes:
    """Schneidet das Thumbnail mittig quadratisch zu (YouTube-Thumbnails sind 16:9) und liefert JPEG-Bytes."""
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        side = min(img.size)
        left = (img.width - side) // 2
        top = (img.height - side) // 2
        img = img.crop((left, top, left + side, top + side))
        if side > COVER_SIZE:
            img = img.resize((COVER_SIZE, COVER_SIZE), Image.LANCZOS)
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()


def _date(item: Item) -> str:
    return item.date if item.mode != MUSIK and item.date else item.year


def _comment(item: Item) -> str:
    return item.description if item.mode != MUSIK and item.description else item.url


def write_tags(path: Path, item: Item, cover: Path | None = None) -> None:
    if path.suffix.lower() == ".m4a":
        _write_mp4(path, item, cover)
    else:
        _write_id3(path, item, cover)


def _write_mp4(path: Path, item: Item, cover: Path | None) -> None:
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
        tags["covr"] = [MP4Cover(square_cover(cover), imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


def _write_id3(mp3: Path, item: Item, cover: Path | None) -> None:
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
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=square_cover(cover)))
    tags.save(mp3, v2_version=4)
