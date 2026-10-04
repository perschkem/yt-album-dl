"""Weboberfläche (FastAPI) – Start mit `uv run ytdl-web`."""

from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import load_config
from .downloader import ffmpeg_available, probe
from .jobs import JobManager
from .metadata import MUSIK, PODCAST, Item

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


def _check_mode(mode: str) -> None:
    if mode not in (MUSIK, PODCAST):
        raise HTTPException(400, f"Unbekannter Modus: {mode}")


@app.get("/api/config")
def get_config() -> dict:
    return {
        "musik_dir": str(cfg.musik_dir),
        "podcast_dir": str(cfg.podcast_dir),
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


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


def main() -> None:
    print(f"ytdl läuft auf http://localhost:{cfg.port}")
    print(f"  Musik:    {cfg.musik_dir}")
    print(f"  Podcasts: {cfg.podcast_dir}")
    if not ffmpeg_available(cfg):
        print("  WARNUNG: ffmpeg nicht gefunden – bitte installieren: sudo apt install ffmpeg")
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="warning")
