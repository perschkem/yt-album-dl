"""ID3-Tags und Cover in MP3-Dateien schreiben."""

from __future__ import annotations

import io
from pathlib import Path

from mutagen.id3 import APIC, COMM, ID3, TALB, TCMP, TCON, TDRC, TIT2, TPE1, TPE2, TRCK, WOAS
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


def write_tags(mp3: Path, item: Item, cover: Path | None = None) -> None:
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
    date = item.date if item.mode != MUSIK and item.date else item.year
    if date:
        tags.add(TDRC(encoding=3, text=date))
    if item.genre:
        tags.add(TCON(encoding=3, text=item.genre))
    if item.url:
        tags.add(WOAS(url=item.url))
    comment = item.description if item.mode != MUSIK and item.description else item.url
    if comment:
        tags.add(COMM(encoding=3, lang="deu", desc="", text=comment))
    if cover and cover.exists():
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=square_cover(cover)))
    tags.save(mp3, v2_version=4)
