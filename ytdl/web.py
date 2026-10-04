"""Weboberfläche (FastAPI) – Start mit `uv run ytdl-web`."""

from __future__ import annotations

from pathlib import Path

import asyncio
import json

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import albumvideo
from .activity import ActivityManager
from .config import load_config
from .downloader import conflicts, ffmpeg_available, probe
from .explorer import is_allowed, open_in_file_manager
from .jobs import JobManager
from .metadata import MUSIK, PODCAST, Item
from .paths import to_windows_path

STATIC_DIR = Path(__file__).parent / "static"

cfg = load_config()
manager = JobManager(cfg)
activities = ActivityManager()
app = FastAPI(title="ytdl")


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
    tracks: list[dict]


def _album_call(func, *args):
    try:
        return func(*args)
    except Exception as exc:
        raise HTTPException(400, str(exc).removeprefix("ERROR: ")) from exc


def _check_mode(mode: str) -> None:
    if mode not in (MUSIK, PODCAST):
        raise HTTPException(400, f"Unbekannter Modus: {mode}")


def _check_format(fmt: str) -> None:
    if fmt not in ("", "mp3", "m4a"):
        raise HTTPException(400, f"Unbekanntes Format: {fmt}")


def _items(req: JobRequest) -> list[Item]:
    return [Item.from_dict({**data, "mode": req.mode, "audio_format": req.audio_format}) for data in req.items]


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


def _start(kind: str, func, *args) -> dict:
    """Startet einen Vorgang im Hintergrund; Fortschritt per GET /api/activities/{id}."""
    return {"activity_id": activities.start(kind, lambda act: func(*args, activity=act)).id}


@app.get("/api/activities/{activity_id}")
def get_activity(activity_id: str) -> dict:
    activity = activities.get(activity_id)
    if activity is None:
        raise HTTPException(404, "Vorgang nicht gefunden")
    return activity.to_dict()


@app.get("/api/activities/{activity_id}/events")
async def activity_events(activity_id: str, request: Request) -> StreamingResponse:
    activity = activities.get(activity_id)
    if activity is None:
        raise HTTPException(404, "Vorgang nicht gefunden")
    return StreamingResponse(_event_stream(request, activity.to_dict, done=lambda d: d["status"] != "läuft"),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


@app.post("/api/probe")
def post_probe(req: ProbeRequest) -> dict:
    _check_mode(req.mode)
    return _start("probe", probe, req.url.strip(), req.mode, cfg)


@app.post("/api/jobs")
def post_job(req: JobRequest) -> dict:
    _check_mode(req.mode)
    _check_format(req.audio_format)
    if not ffmpeg_available(cfg):
        raise HTTPException(400, "ffmpeg fehlt – bitte installieren: sudo apt install ffmpeg")
    items = [i for i in _items(req) if i.on_conflict != "skip"]
    if not items:
        raise HTTPException(400, "Keine Titel ausgewählt")
    return manager.submit(req.title, req.mode, items).to_dict()


@app.post("/api/conflicts")
def post_conflicts(req: JobRequest) -> list[dict]:
    """Welche Zieldateien existieren schon? Grundlage für den Dialog Überschreiben/Überspringen/Beide behalten."""
    _check_mode(req.mode)
    _check_format(req.audio_format)
    return conflicts(_items(req), cfg)


@app.get("/api/jobs")
def get_jobs() -> list[dict]:
    return manager.snapshot()


@app.delete("/api/jobs")
def clear_jobs() -> dict:
    """„Liste leeren“: abgeschlossene Jobs ausblenden. Dateien, Archiv und laufende Jobs bleiben."""
    return {"removed": manager.clear_finished()}


async def _event_stream(request: Request, snapshot, done=lambda data: False, interval: float = 0.25):
    """Server-Sent Events: schickt den Zustand, sobald er sich ändert (plus Keep-alive alle 15 s)."""
    last, idle = None, 0.0
    while not await request.is_disconnected():
        data = snapshot()
        payload = json.dumps(data, ensure_ascii=False)
        if payload != last:
            last, idle = payload, 0.0
            yield f"data: {payload}\n\n"
            if done(data):
                return
        else:
            idle += interval
            if idle >= 15:
                idle = 0.0
                yield ": keep-alive\n\n"
        await asyncio.sleep(interval)


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@app.get("/api/jobs/events")
async def job_events(request: Request) -> StreamingResponse:
    return StreamingResponse(_event_stream(request, manager.snapshot), media_type="text/event-stream",
                             headers=_SSE_HEADERS)


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
    return _start("album-analyse", albumvideo.analyze, req.url.strip(), cfg)


@app.post("/api/album/{video_id}/detect")
def album_detect(video_id: str, req: AlbumDetectRequest) -> dict:
    _album_call(albumvideo.cache_dir, cfg, video_id)  # ID prüfen
    return _start("album-pausen", albumvideo.redetect, cfg, video_id, req.count, req.min_pause,
                  req.sensitivity, req.artist)


@app.post("/api/album/{video_id}/text")
def album_text(video_id: str, req: AlbumTextRequest) -> dict:
    _album_call(albumvideo.cache_dir, cfg, video_id)
    return _start("album-trackliste", albumvideo.from_text, cfg, video_id, req.text, req.artist)


@app.post("/api/album/{video_id}/scan")
def album_scan(video_id: str, req: AlbumScanRequest) -> dict:
    _album_call(albumvideo.cache_dir, cfg, video_id)
    return _start("album-scan", albumvideo.scan_overlays, cfg, video_id, req.artist)


@app.get("/api/album/{video_id}/audio")
def album_audio(video_id: str) -> FileResponse:
    path = _album_call(albumvideo.audio_path, cfg, video_id)
    if not path:
        raise HTTPException(404, "Audio nicht im Zwischenspeicher")
    return FileResponse(path)


def _album_items(video_id: str, req: AlbumJobRequest) -> list[Item]:
    _check_format(req.audio_format)
    if not req.tracks:
        raise HTTPException(400, "Keine Titel")
    return _album_call(albumvideo.build_items, cfg, video_id, req.album, req.album_artist, req.year,
                       req.genre, req.tracks, req.audio_format)


@app.post("/api/album/{video_id}/conflicts")
def album_conflicts(video_id: str, req: AlbumJobRequest) -> list[dict]:
    return conflicts(_album_items(video_id, req), cfg)


@app.post("/api/album/{video_id}/jobs")
def album_job(video_id: str, req: AlbumJobRequest) -> dict:
    items = [i for i in _album_items(video_id, req) if i.on_conflict != "skip"]
    if not items:
        raise HTTPException(400, "Alle Titel übersprungen")
    return manager.submit(req.album or video_id, MUSIK, items).to_dict()


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


def main() -> None:
    print(f"ytdl läuft auf http://localhost:{cfg.port}")
    print(f"  Musik:    {cfg.musik_dir}")
    print(f"  Podcasts: {cfg.podcast_dir}")
    if not ffmpeg_available(cfg):
        print("  WARNUNG: ffmpeg nicht gefunden – bitte installieren: sudo apt install ffmpeg")
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="warning")
