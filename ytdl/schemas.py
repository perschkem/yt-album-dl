"""Anfragen an die API (pydantic-Modelle)."""

from __future__ import annotations

from pydantic import BaseModel

from .config import MUSIK


class ProbeRequest(BaseModel):
    url: str
    mode: str = MUSIK


class JobRequest(BaseModel):
    title: str = ""
    mode: str = MUSIK
    audio_format: str = ""  # leer = AUDIO_FORMAT aus .env
    items: list[dict]


class AlbumAnalyzeRequest(BaseModel):
    url: str


class AlbumDetectRequest(BaseModel):
    count: int | None = None
    min_pause: float = 1.0
    sensitivity: float = 25.0
    artist: str = ""


class AlbumTextRequest(BaseModel):
    text: str
    artist: str = ""


class AlbumScanRequest(BaseModel):
    artist: str = ""


class AlbumJobRequest(BaseModel):
    album: str
    album_artist: str
    year: str = ""
    genre: str = ""
    audio_format: str = ""
    cover_url: str = ""
    cover_crop: bool = False
    boundary_source: str = ""
    tracks: list[dict]


class SettingsRequest(BaseModel):
    """Nur gesendete Felder werden geändert (None = unverändert)."""
    musik_dir: str | None = None
    podcast_dir: str | None = None
    audio_format: str | None = None
    bitrate: int | None = None
    parallel_downloads: int | None = None
    parallel_cuts: int | None = None
    max_retries: int | None = None
    cookies_from_browser: str | None = None
    cookies_file: str | None = None
    sleep_seconds: int | None = None


class CoverRequest(BaseModel):
    url: str


class OpenRequest(BaseModel):
    path: str


class RetryRequest(BaseModel):
    task_id: str | None = None
