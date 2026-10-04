"""Weboberfläche (FastAPI) – Start mit `uv run ytdl-web`."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import albumvideo, ffmpeg, settings
from .activity import Activity, ActivityManager
from .albumvideo import AlbumCache
from .auth import BROWSERS, friendly_error, youtube
from .config import AUDIO_FORMATS, MissingFolder, load_config, update_env_file
from .covers import CoverError, check_cover, thumbnail_preview
from .downloader import probe
from .errors import clean_error
from .explorer import is_allowed, open_in_file_manager
from .ffmpeg import ffmpeg_available
from .history import History
from .jobs import JobManager
from .library import SKIP, conflicts
from .metadata import MUSIK, PODCAST, Item
from .paths import win_path
from .schemas import (AlbumAnalyzeRequest, AlbumDetectRequest, AlbumJobRequest, AlbumScanRequest, AlbumTextRequest,
                      CoverRequest, JobRequest, OpenRequest, ProbeRequest, RetryRequest, SettingsRequest)
from .status import Status

STATIC_DIR = Path(__file__).parent / "static"
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

cfg = load_config()
history = History(cfg.data_dir)
manager = JobManager(cfg, history=history)
activities = ActivityManager(format_error=friendly_error)
youtube.configure(cfg)
ffmpeg.configure(cfg.ffmpeg_location)
app = FastAPI(title="yt-album-dl")


@app.exception_handler(MissingFolder)
async def missing_folder(request: Request, exc: MissingFolder) -> JSONResponse:
    """Kein Zielordner eingestellt → verständliche 400-Meldung statt Serverfehler."""
    return JSONResponse(status_code=400, content={"detail": str(exc), "missing_folder": True})


@app.exception_handler(CoverError)
async def cover_error(request: Request, exc: CoverError) -> JSONResponse:
    """Cover-URL unbrauchbar – die Meldung ist für die Oberfläche formuliert."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------- Hilfen ----------

def _bad_request(func: Callable, *args):
    """Ruft func auf; Fehler werden zu 400 mit lesbarer Meldung."""
    try:
        return func(*args)
    except Exception as exc:
        raise HTTPException(400, clean_error(exc)) from exc


def _check_mode(mode: str) -> None:
    if mode not in (MUSIK, PODCAST):
        raise HTTPException(400, f"Unbekannter Modus: {mode}")


def _check_format(fmt: str) -> None:
    if fmt and fmt not in AUDIO_FORMATS:
        raise HTTPException(400, f"Unbekanntes Format: {fmt}")


def _items(req: JobRequest) -> list[Item]:
    return [Item.from_dict({**data, "mode": req.mode, "audio_format": req.audio_format}) for data in req.items]


def _submit(title: str, mode: str, items: list[Item], empty_message: str) -> dict:
    """Job anlegen – ohne die Titel, die wegen einer vorhandenen Datei übersprungen werden sollen."""
    items = [i for i in items if i.on_conflict != SKIP]
    if not items:
        raise HTTPException(400, empty_message)
    return manager.submit(title, mode, items).to_dict()


def _start(kind: str, func: Callable, *args) -> dict:
    """Startet einen Vorgang im Hintergrund; Fortschritt per GET /api/activities/{id}."""
    return {"activity_id": activities.start(kind, lambda act: func(*args, activity=act)).id}


def _activity_or_404(activity_id: str) -> Activity:
    activity = activities.get(activity_id)
    if activity is None:
        raise HTTPException(404, "Vorgang nicht gefunden")
    return activity


def album_cache(video_id: str) -> AlbumCache:
    """Pfad-Parameter video_id prüfen (nur YouTube-ID-Zeichen) – als FastAPI-Dependency."""
    try:
        return AlbumCache(cfg, video_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


async def _event_stream(request: Request, snapshot: Callable[[], dict], done=lambda data: False,
                        interval: float = 0.25):
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


def _sse(request: Request, snapshot: Callable[[], dict], done=lambda data: False) -> StreamingResponse:
    return StreamingResponse(_event_stream(request, snapshot, done), media_type="text/event-stream",
                             headers=_SSE_HEADERS)


# ---------- Konfiguration und Einstellungen (werden in .env gespeichert) ----------

@app.get("/api/config")
def get_config() -> dict:
    return {
        "musik_dir": win_path(cfg.musik_dir),
        "podcast_dir": win_path(cfg.podcast_dir),
        "audio_format": cfg.audio_format,
        "parallel_downloads": cfg.parallel_downloads,
        "bitrate": cfg.bitrate,
        "ffmpeg": ffmpeg_available(cfg),
    }


@app.get("/api/settings")
def get_settings() -> dict:
    return {**settings.current(cfg), "bitrates": settings.BITRATES, "browsers": BROWSERS, "limits": settings.limits()}


@app.put("/api/settings")
def put_settings(req: SettingsRequest) -> dict:
    try:
        env, changes = settings.validate(req.model_dump(exclude_none=True))
    except settings.InvalidSettings as exc:
        raise HTTPException(400, {"message": str(exc), "fields": exc.fields}) from exc
    update_env_file(env)
    for field, value in changes.items():  # sofort wirksam, ohne Neustart
        setattr(cfg, field, value)
    manager.ensure_workers()
    youtube.configure(cfg)
    return get_settings()


@app.get("/api/auth")
def get_auth() -> dict:
    """Status der YouTube-Anmeldung: Bot-Prüfung zuletzt? Laufen Downloads gerade mit Cookies?"""
    return youtube.status()


# ---------- Hintergrund-Vorgänge ----------

@app.get("/api/activities/{activity_id}")
def get_activity(activity_id: str) -> dict:
    return _activity_or_404(activity_id).to_dict()


@app.get("/api/activities/{activity_id}/events")
async def activity_events(activity_id: str, request: Request) -> StreamingResponse:
    activity = _activity_or_404(activity_id)
    return _sse(request, activity.to_dict, done=lambda d: d["status"] != Status.RUNNING)


@app.post("/api/probe")
def post_probe(req: ProbeRequest) -> dict:
    _check_mode(req.mode)
    return _start("probe", probe, req.url.strip(), req.mode, cfg)


# ---------- Downloads ----------

@app.post("/api/jobs")
def post_job(req: JobRequest) -> dict:
    _check_mode(req.mode)
    _check_format(req.audio_format)
    if not ffmpeg_available(cfg):
        raise HTTPException(400, "ffmpeg fehlt – bitte installieren: sudo apt install ffmpeg")
    return _submit(req.title, req.mode, _items(req), "Keine Titel ausgewählt")


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


@app.get("/api/jobs/events")
async def job_events(request: Request) -> StreamingResponse:
    """Live-Updates: Job-Liste plus Anmeldestatus (für den Hinweis bei einer YouTube-Bot-Prüfung)."""
    return _sse(request, lambda: {"jobs": manager.snapshot(), "auth": youtube.status()})


@app.post("/api/jobs/resume")
def resume_jobs() -> dict:
    """Pause wegen YouTube-Bot-Prüfung aufheben und pausierte Titel sofort neu versuchen."""
    return {"resumed": manager.resume()}


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str, req: RetryRequest) -> dict:
    try:
        return manager.retry(job_id, req.task_id)
    except KeyError as exc:
        raise HTTPException(404, "Job nicht gefunden") from exc


@app.post("/api/open")
def open_path(req: OpenRequest) -> dict:
    path = Path(req.path)
    if not (is_allowed(path, cfg.roots() + manager.known_roots()) or history.knows_path(path)):
        raise HTTPException(403, "Nur Dateien in den Musik-/Podcast-Ordnern können geöffnet werden")
    return {"opened": _bad_request(open_in_file_manager, path)}


# ---------- Cover ----------

@app.post("/api/cover/check")
def cover_check(req: CoverRequest) -> dict:
    """Prüft eine Cover-URL (ist es wirklich ein Bild?) – für die Vorschau neben dem Feld."""
    return check_cover(req.url)


@app.get("/api/cover/thumbnail")
def cover_thumbnail(src: str) -> Response:
    """Vorschau: YouTube-Vorschaubild mit entfernten schwarzen Balken, quadratisch – wie es eingebettet wird."""
    return Response(thumbnail_preview(src), media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


# ---------- Album in einem Video ----------

@app.post("/api/album/analyze")
def album_analyze(req: AlbumAnalyzeRequest) -> dict:
    return _start("album-analyse", albumvideo.analyze, req.url.strip(), cfg)


@app.post("/api/album/{video_id}/detect")
def album_detect(req: AlbumDetectRequest, cache: AlbumCache = Depends(album_cache)) -> dict:
    return _start("album-pausen", albumvideo.redetect, cfg, cache.video_id, req.count, req.min_pause,
                  req.sensitivity, req.artist)


@app.post("/api/album/{video_id}/text")
def album_text(req: AlbumTextRequest, cache: AlbumCache = Depends(album_cache)) -> dict:
    return _start("album-trackliste", albumvideo.from_text, cfg, cache.video_id, req.text, req.artist)


@app.post("/api/album/{video_id}/scan")
def album_scan(req: AlbumScanRequest, cache: AlbumCache = Depends(album_cache)) -> dict:
    return _start("album-scan", albumvideo.scan_overlays, cfg, cache.video_id, req.artist)


@app.get("/api/album/{video_id}/audio")
def album_audio(cache: AlbumCache = Depends(album_cache)) -> FileResponse:
    if not (path := cache.audio):
        raise HTTPException(404, "Audio nicht im Zwischenspeicher")
    return FileResponse(path)


def _album_items(cache: AlbumCache, req: AlbumJobRequest) -> list[Item]:
    _check_format(req.audio_format)
    if not req.tracks:
        raise HTTPException(400, "Keine Titel")
    return _bad_request(albumvideo.build_items, cfg, cache.video_id, req.album, req.album_artist, req.year,
                        req.genre, req.tracks, req.audio_format, req.cover_url, req.cover_crop, req.boundary_source)


@app.post("/api/album/{video_id}/conflicts")
def album_conflicts(req: AlbumJobRequest, cache: AlbumCache = Depends(album_cache)) -> list[dict]:
    return conflicts(_album_items(cache, req), cfg)


@app.post("/api/album/{video_id}/jobs")
def album_job(req: AlbumJobRequest, cache: AlbumCache = Depends(album_cache)) -> dict:
    return _submit(req.album or cache.video_id, MUSIK, _album_items(cache, req), "Alle Titel übersprungen")


# ---------- Historie ----------

def _history_filters(q: str, mode: str, result: str, days: int | None) -> dict:
    return {"q": q, "mode": mode, "result": result, "since": time.time() - days * 86400 if days else None}


@app.get("/api/history")
def get_history(q: str = "", mode: str = "", result: str = "", days: int | None = None,
                limit: int = 20, offset: int = 0) -> dict:
    """Nach Download gruppiert (wie die Download-Liste); Titel einer Gruppe in Job-Reihenfolge."""
    return history.query_groups(limit=max(1, min(limit, 200)), offset=max(0, offset),
                                **_history_filters(q, mode, result, days))


@app.get("/api/history.csv")
def get_history_csv(q: str = "", mode: str = "", result: str = "", days: int | None = None) -> Response:
    csv_text = history.to_csv(**_history_filters(q, mode, result, days))
    return Response("﻿" + csv_text, media_type="text/csv; charset=utf-8",  # BOM, damit Excel Umlaute erkennt
                    headers={"Content-Disposition": 'attachment; filename="yt-album-dl-historie.csv"'})


@app.delete("/api/history")
def clear_history() -> dict:
    return {"removed": history.clear()}


@app.get("/historie", include_in_schema=False)
def history_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "historie.html")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


def main() -> None:
    print(f"yt-album-dl läuft auf http://localhost:{cfg.port}")
    print(f"  Musik:    {cfg.musik_dir or '– nicht eingestellt (⚙ Einstellungen) –'}")
    print(f"  Podcasts: {cfg.podcast_dir or '– nicht eingestellt (⚙ Einstellungen) –'}")
    if not ffmpeg_available(cfg):
        print("  WARNUNG: ffmpeg nicht gefunden – bitte installieren: sudo apt install ffmpeg")
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="warning")
