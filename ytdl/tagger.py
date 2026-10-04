"""Tags und Cover schreiben: ID3 für MP3, MP4-Atome für M4A."""

from __future__ import annotations

from pathlib import Path

from mutagen.id3 import APIC, COMM, ID3, TALB, TCMP, TCON, TDRC, TIT2, TPE1, TPE2, TRCK, WOAS
from mutagen.mp4 import MP4, MP4Cover

from .covers import cover_jpeg
from .metadata import MUSIK, Item

VARIOUS_ARTISTS = "Various Artists"


def _date(item: Item) -> str:
    return item.date if item.mode != MUSIK and item.date else item.year


def _comment(item: Item) -> str:
    return item.description if item.mode != MUSIK and item.description else item.url


def tag_values(item: Item) -> dict:
    """Die zu schreibenden Werte, unabhängig vom Format; None = Tag wird nicht gesetzt."""
    return {
        "title": item.title,
        "artist": item.artist,
        "album_artist": item.album_artist or item.artist,
        "album": item.album or None,
        # Sampler/Compilation – Player gruppieren das Album dann richtig
        "compilation": item.album_artist == VARIOUS_ARTISTS,
        "track": (item.track_no, item.track_total) if item.track_no else None,
        "date": _date(item) or None,
        "genre": item.genre or None,
        "comment": _comment(item) or None,
        "url": item.url or None,
    }


def write_tags(path: Path, item: Item, cover: Path | None = None, crop: bool = True) -> None:
    values = tag_values(item)
    image = cover_jpeg(cover, crop) if cover and cover.exists() else None
    if path.suffix.lower() == ".m4a":
        _write_mp4(path, values, image)
    else:
        _write_id3(path, values, image)


_MP4_TEXT = {"title": "\xa9nam", "artist": "\xa9ART", "album_artist": "aART", "album": "\xa9alb", "date": "\xa9day",
             "genre": "\xa9gen", "comment": "\xa9cmt"}
_ID3_TEXT = {"title": TIT2, "artist": TPE1, "album_artist": TPE2, "album": TALB, "date": TDRC, "genre": TCON}


def _write_mp4(path: Path, values: dict, image: bytes | None) -> None:
    audio = MP4(path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    tags.clear()
    for key, atom in _MP4_TEXT.items():
        if values[key] is not None:
            tags[atom] = [values[key]]
    if values["compilation"]:
        tags["cpil"] = True
    if values["track"]:
        number, total = values["track"]
        tags["trkn"] = [(number, total or 0)]
    if image:
        tags["covr"] = [MP4Cover(image, imageformat=MP4Cover.FORMAT_JPEG)]
    audio.save()


def _write_id3(mp3: Path, values: dict, image: bytes | None) -> None:
    tags = ID3()
    for key, frame in _ID3_TEXT.items():
        if values[key] is not None:
            tags.add(frame(encoding=3, text=values[key]))
    if values["compilation"]:
        tags.add(TCMP(encoding=3, text="1"))
    if values["track"]:
        number, total = values["track"]
        tags.add(TRCK(encoding=3, text=f"{number}/{total}" if total else str(number)))
    if values["url"]:
        tags.add(WOAS(url=values["url"]))
    if values["comment"]:
        tags.add(COMM(encoding=3, lang="deu", desc="", text=values["comment"]))
    if image:
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=image))
    tags.save(mp3, v2_version=4)
