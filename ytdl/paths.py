"""Windows-sichere Dateinamen und Zielpfade."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .metadata import MUSIK, Item, primary_artist

MAX_COMPONENT = 120
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_REPLACEMENTS = {
    ":": " -",
    "/": "-",
    "\\": "-",
    "|": "-",
    '"': "'",
    "?": "",
    "*": "",
    "<": "",
    ">": "",
}


def sanitize(name: str, fallback: str = "Unbekannt") -> str:
    """Macht aus einem beliebigen Text einen gültigen Datei-/Ordnernamen für Windows (NTFS)."""
    for bad, good in _REPLACEMENTS.items():
        name = name.replace(bad, good)
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > MAX_COMPONENT:
        name = name[:MAX_COMPONENT].rstrip()
    name = name.rstrip(". ")
    if not name:
        return fallback
    if name.split(".")[0].upper() in _RESERVED:
        name += "_"
    return name


def music_path(item: Item, root: Path) -> Path:
    """Musik/<Albuminterpret>/<Album> (<Jahr>)/01 - Interpret - Titel.mp3
    bzw. Musik/<Interpret>/Singles/Interpret - Titel.mp3"""
    base = f"{item.artist} - {item.title}"
    if item.album:
        album_dir = f"{item.album} ({item.year})" if item.year else item.album
        folder = root / sanitize(item.album_artist or primary_artist(item.artist)) / sanitize(album_dir)
        if item.track_no:
            width = max(2, len(str(item.track_total or 0)))
            base = f"{item.track_no:0{width}d} - {base}"
    else:
        folder = root / sanitize(primary_artist(item.artist)) / "Singles"
    return folder / f"{sanitize(base)}.mp3"


def podcast_path(item: Item, root: Path) -> Path:
    """Podcasts/<Kanal>/<YYYY-MM-DD> - <Titel>.mp3"""
    base = f"{item.date} - {item.title}" if item.date else item.title
    return root / sanitize(item.artist) / f"{sanitize(base)}.mp3"


def target_path(item: Item, root: Path) -> Path:
    return music_path(item, root) if item.mode == MUSIK else podcast_path(item, root)


_WSL_MOUNT = re.compile(r"^/mnt/([a-z])(?:/(.*))?$")


def to_windows_path(path: Path) -> str:
    """/mnt/d/Musik/x.mp3 → D:\\Musik\\x.mp3 (WSL-Laufwerk); andere Pfade bleiben unverändert."""
    match = _WSL_MOUNT.match(path.as_posix())
    if not match:
        return str(path)
    drive, rest = match.groups()
    return f"{drive.upper()}:\\" + (rest or "").replace("/", "\\")


def win_path(path: str | Path | None) -> str:
    """Wie to_windows_path, aber leer, wenn kein Pfad da ist (für die Anzeige in der Oberfläche)."""
    return to_windows_path(Path(path)) if path else ""


def common_folder(paths: list[str]) -> str:
    """Gemeinsamer Ordner mehrerer Dateien (z.B. Album-/Kanalordner); leer, wenn keine Dateien."""
    if not paths:
        return ""
    return os.path.commonpath([str(Path(p).parent) for p in paths])
