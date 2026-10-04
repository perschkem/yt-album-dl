"""Weboberfläche (FastAPI) – Start mit `uv run ytdl-web`."""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import albumvideo
from .config import load_config
from .downloader import ffmpeg_available, probe
from .explorer import is_allowed, open_in_file_manager
from .jobs import JobManager
from .metadata import MUSIK, PODCAST, Item
from .paths import to_windows_path

STATIC_DIR = Path(__file__).parent / "static"

cfg = load_config()
manager = JobManager(cfg)
app = FastAPI(title="ytdl")


class ProbeRequest(BaseModel):
    url: str
    mode: str = MUSIK


class JobRequest(BaseModel):
    title: str = ""
    mode: str = MUSIK
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
    tracks: list[dict]


def _album_call(func, *args):
    try:
        return func(*args)
    except Exception as exc:
        raise HTTPException(400, str(exc).removeprefix("ERROR: ")) from exc


def _check_mode(mode: str) -> None:
    if mode not in (MUSIK, PODCAST):
        raise HTTPException(400, f"Unbekannter Modus: {mode}")


@app.get("/api/config")
def get_config() -> dict:
    return {
        "musik_dir": to_windows_path(cfg.musik_dir),
        "podcast_dir": to_windows_path(cfg.podcast_dir),
        "audio_format": cfg.audio_format,
        "parallel_downloads": cfg.parallel_downloads,
        "bitrate": cfg.bitrate,
        "ffmpeg": ffmpeg_available(cfg),
    }


@app.post("/api/probe")
def post_probe(req: ProbeRequest) -> dict:
    _check_mode(req.mode)
    try:
        return probe(req.url.strip(), req.mode, cfg)
    except Exception as exc:
        raise HTTPException(400, str(exc).removeprefix("ERROR: ")) from exc


@app.post("/api/jobs")
def post_job(req: JobRequest) -> dict:
    _check_mode(req.mode)
    if not ffmpeg_available(cfg):
        raise HTTPException(400, "ffmpeg fehlt – bitte installieren: sudo apt install ffmpeg")
    items = [Item.from_dict({**data, "mode": req.mode}) for data in req.items]
    if not items:
        raise HTTPException(400, "Keine Titel ausgewählt")
    return manager.submit(req.title, req.mode, items).to_dict()


@app.get("/api/jobs")
def get_jobs() -> list[dict]:
    return manager.snapshot()


class OpenRequest(BaseModel):
    path: str


@app.post("/api/open")
def open_path(req: OpenRequest) -> dict:
    path = Path(req.path)
    if not is_allowed(path, [cfg.musik_dir, cfg.podcast_dir]):
        raise HTTPException(403, "Nur Dateien in den Musik-/Podcast-Ordnern können geöffnet werden")
    try:
        return {"opened": open_in_file_manager(path)}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


class RetryRequest(BaseModel):
    task_id: str | None = None


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str, req: RetryRequest) -> dict:
    try:
        return manager.retry(job_id, req.task_id)
    except KeyError as exc:
        raise HTTPException(404, "Job nicht gefunden") from exc


@app.post("/api/album/analyze")
def album_analyze(req: AlbumAnalyzeRequest) -> dict:
    return _album_call(albumvideo.analyze, req.url.strip(), cfg)


@app.post("/api/album/{video_id}/detect")
def album_detect(video_id: str, req: AlbumDetectRequest) -> dict:
    return _album_call(albumvideo.redetect, cfg, video_id, req.count, req.min_pause, req.sensitivity, req.artist)


@app.post("/api/album/{video_id}/text")
def album_text(video_id: str, req: AlbumTextRequest) -> dict:
    return _album_call(albumvideo.from_text, cfg, video_id, req.text, req.artist)


@app.post("/api/album/{video_id}/scan")
def album_scan(video_id: str, req: AlbumScanRequest) -> dict:
    return _album_call(albumvideo.scan_overlays, cfg, video_id, req.artist)


@app.get("/api/album/{video_id}/audio")
def album_audio(video_id: str) -> FileResponse:
    path = _album_call(albumvideo.audio_path, cfg, video_id)
    if not path:
        raise HTTPException(404, "Audio nicht im Zwischenspeicher")
    return FileResponse(path)


@app.post("/api/album/{video_id}/jobs")
def album_job(video_id: str, req: AlbumJobRequest) -> dict:
    if not req.tracks:
        raise HTTPException(400, "Keine Titel")
    items = _album_call(albumvideo.build_items, cfg, video_id, req.album, req.album_artist, req.year,
                        req.genre, req.tracks)
    return manager.submit(req.album or video_id, MUSIK, items).to_dict()


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


def main() -> None:
    print(f"ytdl läuft auf http://localhost:{cfg.port}")
    print(f"  Musik:    {cfg.musik_dir}")
    print(f"  Podcasts: {cfg.podcast_dir}")
    if not ffmpeg_available(cfg):
        print("  WARNUNG: ffmpeg nicht gefunden – bitte installieren: sudo apt install ffmpeg")
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="warning")
