"""Konfiguration aus .env / Umgebungsvariablen – änderbar über die Oberfläche (⚙ Einstellungen)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# YTDL_ENV_FILE erlaubt eine andere Datei (z.B. für Tests, damit die echte .env unangetastet bleibt)
ENV_FILE = Path(os.getenv("YTDL_ENV_FILE") or PROJECT_ROOT / ".env")

_WIN_DRIVE = re.compile(r"^([A-Za-z]):[\\/]*(.*)$")


def to_local_path(value: str) -> Path:
    """Wandelt einen Windows-Pfad (D:\\Musik) in einen WSL-Pfad (/mnt/d/Musik) um.

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


def optional_path(value: str | None) -> Path | None:
    """Leerer Wert = nicht eingestellt (es gibt bewusst keinen Standardordner)."""
    return to_local_path(value) if value and value.strip() else None


@dataclass
class Config:
    musik_dir: Path | None
    podcast_dir: Path | None
    data_dir: Path
    bitrate: int
    host: str
    port: int
    ffmpeg_location: str | None
    parallel_downloads: int = 3
    parallel_cuts: int = 4
    max_retries: int = 5
    audio_format: str = "mp3"  # mp3 | m4a

    def root(self, mode: str) -> Path:
        """Zielordner für einen Modus; Fehler mit Hinweis auf die Einstellungen, wenn keiner gesetzt ist."""
        from .metadata import MUSIK

        root = self.musik_dir if mode == MUSIK else self.podcast_dir
        if root is None:
            name = "Musik" if mode == MUSIK else "Podcasts"
            raise MissingFolder(f"Kein Ordner für {name} eingestellt – bitte unter ⚙ Einstellungen festlegen")
        return root

    def roots(self) -> list[Path]:
        return [p for p in (self.musik_dir, self.podcast_dir) if p is not None]


class MissingFolder(ValueError):
    pass


def load_config() -> Config:
    load_dotenv(ENV_FILE)
    ffmpeg = os.getenv("FFMPEG_LOCATION", "").strip()
    return Config(
        musik_dir=optional_path(os.getenv("MUSIK_DIR")),
        podcast_dir=optional_path(os.getenv("PODCAST_DIR")),
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


# ---------- .env schreiben ----------

def _env_value(value: str) -> str:
    """Wert für .env: einfache Anführungszeichen sind in python-dotenv wörtlich (Backslashes in Windows-Pfaden
    bleiben erhalten); nur nötig bei Leerzeichen, # oder Anführungszeichen."""
    if value == "" or not re.search(r"[\s#'\"]", value):
        return value
    if "'" not in value:
        return f"'{value}'"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def update_env_file(values: dict[str, str], path: Path = ENV_FILE) -> None:
    """Setzt Variablen in .env: vorhandene Zeilen werden ersetzt, fehlende angehängt; Kommentare und andere
    Zeilen bleiben unverändert. Die Datei wird angelegt, falls es sie noch nicht gibt."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    remaining = dict(values)
    for i, line in enumerate(lines):
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match and match.group(1) in remaining:
            key = match.group(1)
            lines[i] = f"{key}={_env_value(remaining.pop(key))}"
    if remaining:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(f"{key}={_env_value(value)}" for key, value in remaining.items())
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)
    for key, value in values.items():
        os.environ[key] = value
