"""Album in einem Video: analysieren (Grenzen + Titel finden) und in getaggte Einzeltitel schneiden."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
from yt_dlp import YoutubeDL

from .config import Config
from .downloader import Archive, ProgressCallback, _base_opts, _unique
from .metadata import MUSIK, Item, clean_title, music_item, normalize_feat, split_artist_title
from .ocr import overlay_titles, tracklist_from_frames
from .paths import target_path
from .split import (
    FPS,
    Segment,
    cut,
    detect_boundaries,
    envelope,
    parse_titles,
    parse_tracklist,
    peaks,
    segments_from_boundaries,
    segments_from_chapters,
    snap,
)
from .tagger import write_tags

CACHE_DAYS = 7
SOURCE_LABELS = {
    "kapitel": "YouTube-Kapitel",
    "beschreibung": "Zeitstempel in der Beschreibung",
    "bild": "Trackliste im Videobild (OCR)",
    "kommentar": "Zeitstempel in einem Kommentar",
    "einblendung": "Titeleinblendungen im Video (OCR)",
    "eingabe": "eingefügte Trackliste",
    "stille": "Pausenerkennung im Audio",
}
_ALBUM_NOISE = re.compile(
    r"\b(full\s+(album|playlist)|playlist|greatest\s+hits\s+full|best\s+songs?\s+of|all\s+time|"
    r"(19|20)\d{2}|top\s+\d+|hq|hd)\b",
    re.IGNORECASE,
)


def cache_dir(cfg: Config, video_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", video_id):
        raise ValueError("Ungültige Video-ID")
    return cfg.data_dir / "cache" / video_id


def cleanup_cache(cfg: Config) -> None:
    root = cfg.data_dir / "cache"
    if not root.exists():
        return
    limit = time.time() - CACHE_DAYS * 86400
    for entry in root.iterdir():
        if entry.is_dir() and entry.stat().st_mtime < limit:
            shutil.rmtree(entry, ignore_errors=True)


def _audio_file(folder: Path) -> Path | None:
    return next((p for p in folder.glob("audio.*") if not p.name.endswith((".part", ".ytdl"))), None)


def _fetch_audio(info: dict, folder: Path) -> Path:
    """Lädt die Audiospur einmal in den Zwischenspeicher (für Vorschau-Player, Analyse und Schnitt)."""
    if audio := _audio_file(folder):
        return audio
    folder.mkdir(parents=True, exist_ok=True)
    opts = {
        **_base_opts(),
        "ignoreerrors": False,
        # m4a/webm spielen alle Browser ab
        "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
        "outtmpl": str(folder / "audio.%(ext)s"),
        "writethumbnail": True,
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([info["webpage_url"]])
    audio = _audio_file(folder)
    if not audio:
        raise RuntimeError("Audio konnte nicht geladen werden")
    return audio


def _envelope(folder: Path, audio: Path) -> np.ndarray:
    path = folder / "envelope.npy"
    if path.exists():
        return np.load(path)
    env = envelope(audio)
    np.save(path, env)
    return env


def _comment_tracklist(url: str, duration: float) -> list[Segment]:
    opts = {
        **_base_opts(),
        "getcomments": True,
        "extractor_args": {"youtube": {"max_comments": ["60"], "comment_sort": ["top"]}},
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}
    comments = sorted(
        info.get("comments") or [],
        key=lambda c: (not c.get("is_pinned"), not c.get("author_is_uploader"), -(c.get("like_count") or 0)),
    )
    best: list[Segment] = []
    for comment in comments:
        segments = parse_tracklist(comment.get("text") or "", duration)
        if len(segments) > len(best):
            best = segments
    return best


def _guess_album(title: str) -> str:
    lower = title.lower()
    for phrase, album in (("greatest hits", "Greatest Hits"), ("best of", "Best Of"), ("the very best", "The Very Best")):
        if phrase in lower:
            return album
    part = re.split(r"\s+[|•]\s+", clean_title(title))[0]
    parsed = split_artist_title(part)
    if parsed:
        part = parsed[1]
    part = _ALBUM_NOISE.sub("", part)
    return re.sub(r"\s{2,}", " ", part).strip(" -–—|()[]") or "Unbekanntes Album"


def _tracks(segments: list[Segment], default_artist: str) -> list[dict]:
    """Segmente → Trackzeilen; 'Interpret - Titel' im Text wird zerlegt."""
    tracks = []
    for seg in segments:
        artist, title = default_artist, clean_title(seg.title)
        if parsed := split_artist_title(title):
            artist, title = parsed
        tracks.append({"start": round(seg.start, 2), "end": round(seg.end, 2),
                       "artist": normalize_feat(artist), "title": title})
    return tracks


def _save_meta(folder: Path, meta: dict) -> None:
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def load_meta(cfg: Config, video_id: str) -> dict:
    path = cache_dir(cfg, video_id) / "meta.json"
    if not path.exists():
        raise ValueError("Video nicht analysiert – bitte erneut prüfen")
    return json.loads(path.read_text(encoding="utf-8"))


def analyze(url: str, cfg: Config) -> dict:
    """Findet Trackgrenzen und Titel. Reihenfolge: Kapitel → Beschreibung → Bild (OCR) → Kommentare → Pausen."""
    cleanup_cache(cfg)
    with YoutubeDL(_base_opts()) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise ValueError("Keine Informationen gefunden – ist die URL korrekt?")

    folder = cache_dir(cfg, info["id"])
    audio = _fetch_audio(info, folder)
    env = _envelope(folder, audio)
    duration = float(info.get("duration") or len(env) / FPS)

    hints: list[str] = []
    source = "stille"
    segments: list[Segment] = []
    if len(info.get("chapters") or []) >= 2:
        source, segments = "kapitel", segments_from_chapters(info["chapters"], duration)
    if not segments and (segments := parse_tracklist(info.get("description") or "", duration)):
        source = "beschreibung"
    if not segments:
        segments, hints = tracklist_from_frames(info, duration)
        source = "bild" if segments else source
    if not segments and (segments := _comment_tracklist(info["webpage_url"], duration)):
        source = "kommentar"
    if segments and source != "kapitel":
        segments = snap(segments, env)
    if not segments:
        segments = segments_from_boundaries(detect_boundaries(env), duration)

    base = music_item(info)
    artist = base.artist
    # Interpret im Bild (z.B. "DIRE STRAITS" über der Trackliste) ist meist zuverlässiger als der Videotitel
    if hints:
        big = [h for h in hints if len(h) > 3 and h.isupper()]
        if big:
            artist = big[0].title()

    meta = {
        "id": info["id"],
        "url": info["webpage_url"],
        "title": info.get("title") or "",
        "duration": duration,
        "thumbnail": info.get("thumbnail") or "",
        "year": base.year,
    }
    _save_meta(folder, meta)
    return {
        **meta,
        "source": source,
        "source_label": SOURCE_LABELS[source],
        "artist": artist,
        "album": _guess_album(meta["title"]),
        "hints": hints,
        "tracks": _tracks(segments, artist),
        "peaks": peaks(env),
        "audio_url": f"/api/album/{info['id']}/audio",
    }


def redetect(cfg: Config, video_id: str, count: int | None, min_pause: float, sensitivity: float,
             artist: str) -> dict:
    folder = cache_dir(cfg, video_id)
    meta = load_meta(cfg, video_id)
    env = _envelope(folder, _audio_file(folder))
    cuts = detect_boundaries(env, count=count, min_pause=min_pause, sensitivity_db=sensitivity)
    segments = segments_from_boundaries(cuts, meta["duration"])
    return {"source": "stille", "source_label": SOURCE_LABELS["stille"], "tracks": _tracks(segments, artist)}


def from_text(cfg: Config, video_id: str, text: str, artist: str) -> dict:
    """Eingefügte Trackliste: mit Zeitstempeln → direkt übernehmen; nur Titel → so viele Grenzen suchen."""
    folder = cache_dir(cfg, video_id)
    meta = load_meta(cfg, video_id)
    env = _envelope(folder, _audio_file(folder))
    if segments := parse_tracklist(text, meta["duration"]):
        segments = snap(segments, env)
    else:
        titles = parse_titles(text)
        if not titles:
            raise ValueError("Keine Titel im Text gefunden")
        cuts = detect_boundaries(env, count=len(titles)) if len(titles) > 1 else []
        segments = segments_from_boundaries(cuts, meta["duration"])
        for seg, title in zip(segments, titles):
            seg.title = title
    return {"source": "eingabe", "source_label": SOURCE_LABELS["eingabe"], "tracks": _tracks(segments, artist)}


def scan_overlays(cfg: Config, video_id: str, artist: str) -> dict:
    """Langsamer Bild-Scan: Video in 480p laden und alle 10 s die Einblendung lesen."""
    folder = cache_dir(cfg, video_id)
    meta = load_meta(cfg, video_id)
    video = next(folder.glob("video.*"), None)
    if not video:
        opts = {**_base_opts(), "ignoreerrors": False, "format": "bv*[height<=480]/b[height<=480]",
                "outtmpl": str(folder / "video.%(ext)s")}
        with YoutubeDL(opts) as ydl:
            ydl.download([meta["url"]])
        video = next(folder.glob("video.*"), None)
    if not video:
        raise RuntimeError("Video konnte nicht geladen werden")
    segments = overlay_titles(video, meta["duration"])
    if not segments:
        raise ValueError("Keine wechselnden Titeleinblendungen gefunden")
    env = _envelope(folder, _audio_file(folder))
    segments = snap(segments, env, window=8.0)
    return {"source": "einblendung", "source_label": SOURCE_LABELS["einblendung"], "tracks": _tracks(segments, artist)}


def audio_path(cfg: Config, video_id: str) -> Path | None:
    return _audio_file(cache_dir(cfg, video_id))


def build_items(cfg: Config, video_id: str, album: str, album_artist: str, year: str, genre: str,
                tracks: list[dict]) -> list[Item]:
    meta = load_meta(cfg, video_id)
    ordered = sorted(tracks, key=lambda t: float(t["start"]))
    items = []
    for n, track in enumerate(ordered, start=1):
        end = ordered[n]["start"] if n < len(ordered) else meta["duration"]
        items.append(Item(
            id=f"{video_id}-{n:02d}", url=meta["url"], mode=MUSIK,
            title=track["title"].strip() or f"Track {n}",
            artist=(track.get("artist") or album_artist).strip() or "Unbekannt",
            album=album.strip(), album_artist=album_artist.strip(),
            track_no=n, track_total=len(ordered), year=year.strip(), genre=genre.strip(),
            start=float(track["start"]), end=float(end), source_id=video_id,
        ))
    return items


def cut_track(item: Item, cfg: Config, progress: ProgressCallback) -> Path:
    """Schneidet einen Titel aus dem zwischengespeicherten Audio, taggt und legt ihn ab."""
    folder = cache_dir(cfg, item.source_id)
    audio = _audio_file(folder)
    if not audio:
        raise RuntimeError("Zwischengespeichertes Audio fehlt – bitte Video erneut analysieren")
    thumb = next((p for p in folder.iterdir() if p.stem == "audio" and p.suffix.lower() in
                  {".jpg", ".jpeg", ".png", ".webp"}), None)
    progress("schneidet", 10.0)
    with tempfile.TemporaryDirectory(prefix="ytdl-") as tmp:
        mp3 = Path(tmp) / "track.mp3"
        cut(audio, item.start or 0.0, item.end, mp3, cfg.bitrate)
        progress("taggt", 90.0)
        write_tags(mp3, item, thumb)
        target = _unique(target_path(item, cfg.musik_dir, cfg.podcast_dir))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(mp3), target)
    Archive(cfg.data_dir, MUSIK).add(item.source_id)
    progress("fertig", 100.0)
    return target
