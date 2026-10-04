"""Welches ffmpeg? FFMPEG_LOCATION (Ordner oder Datei) oder das ffmpeg im PATH – für alle Aufrufe gleich."""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import Config

_location: str | None = None  # beim Start aus der Konfiguration gesetzt


def configure(location: str | None) -> None:
    global _location
    _location = location or None


def location() -> str | None:
    """FFMPEG_LOCATION, wie eingestellt (für yt-dlp); None = ffmpeg aus dem PATH."""
    return _location


def executable(location: str | None = None) -> str:
    """Pfad zum ffmpeg-Programm; ohne Einstellung einfach „ffmpeg“ (wird im PATH gesucht)."""
    loc = location or _location
    if not loc:
        return "ffmpeg"
    path = Path(loc)
    return str(path / "ffmpeg") if path.is_dir() else str(path)


def ffmpeg_available(cfg: Config) -> bool:
    if cfg.ffmpeg_location:
        return Path(executable(cfg.ffmpeg_location)).is_file()
    return shutil.which("ffmpeg") is not None
