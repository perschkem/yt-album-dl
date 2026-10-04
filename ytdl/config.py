"""Konfiguration aus .env / Umgebungsvariablen."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_WIN_DRIVE = re.compile(r"^([A-Za-z]):[\\/]*(.*)$")


def to_local_path(value: str) -> Path:
    """Wandelt einen Windows-Pfad (D:\\Musik\\...) in einen WSL-Pfad (/mnt/d/Musik/...) um.

    Linux-Pfade bleiben unverändert; relative Pfade werden relativ zum Projektordner aufgelöst.
    """
    value = value.strip().strip('"').strip("'")
    match = _WIN_DRIVE.match(value)
    if match and os.name != "nt":
        drive, rest = match.groups()
        parts = [p for p in re.split(r"[\\/]+", rest) if p]
        return Path("/mnt", drive.lower(), *parts)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


@dataclass(frozen=True)
class Config:
    musik_dir: Path
    podcast_dir: Path
    data_dir: Path
    bitrate: int
    host: str
    port: int
    ffmpeg_location: str | None
    parallel_downloads: int = 3
    parallel_cuts: int = 4
    max_retries: int = 5
    audio_format: str = "mp3"  # mp3 | m4a


def load_config() -> Config:
    load_dotenv(PROJECT_ROOT / ".env")
    ffmpeg = os.getenv("FFMPEG_LOCATION", "").strip()
    return Config(
        musik_dir=to_local_path(os.getenv("MUSIK_DIR", r"D:\Musik")),
        podcast_dir=to_local_path(os.getenv("PODCAST_DIR", r"D:\Podcasts")),
        data_dir=to_local_path(os.getenv("DATA_DIR", "data")),
        bitrate=int(os.getenv("BITRATE", "320")),
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        ffmpeg_location=str(to_local_path(ffmpeg)) if ffmpeg else None,
        parallel_downloads=max(1, int(os.getenv("PARALLEL_DOWNLOADS", "3"))),
        parallel_cuts=max(1, int(os.getenv("PARALLEL_CUTS", str(os.cpu_count() or 2)))),
        max_retries=max(0, int(os.getenv("MAX_RETRIES", "5"))),
        audio_format=_audio_format(os.getenv("AUDIO_FORMAT", "mp3")),
    )


def _audio_format(value: str) -> str:
    value = value.strip().lower()
    if value not in ("mp3", "m4a"):
        raise ValueError(f"AUDIO_FORMAT muss mp3 oder m4a sein, nicht {value!r}")
    return value
