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

from .activity import Activity, NullActivity
from .config import Config
from .downloader import (Archive, ProgressCallback, _base_opts, _extract, audio_format, choose_cover, place,
                         with_cookie_fallback)
from .metadata import MUSIK, Item, clean_title, music_item, normalize_feat, split_artist_title
from .ocr import overlay_titles, tracklist_from_frames
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
from .status import Status
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


_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _audio_file(folder: Path) -> Path | None:
    """Die Audiospur im Zwischenspeicher – nicht das gleichnamige Vorschaubild (audio.webp/.jpg)."""
    return next((p for p in sorted(folder.glob("audio.*"))
                 if p.suffix.lower() not in _IMAGE_SUFFIXES and not p.name.endswith((".part", ".ytdl"))), None)


def _thumbnail_file(folder: Path) -> Path | None:
    return next((p for p in sorted(folder.glob("audio.*")) if p.suffix.lower() in _IMAGE_SUFFIXES), None)


def _mb(value: float | None) -> str:
    return f"{(value or 0) / 1_048_576:.1f}"


def _download_hook(step):
    def hook(d: dict) -> None:
        if d["status"] != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        done = d.get("downloaded_bytes", 0)
        detail = f"{_mb(done)} von {_mb(total)} MB" if total else f"{_mb(done)} MB"
        if d.get("speed"):
            detail += f" · {_mb(d['speed'])} MB/s"
        step.update(detail, done / total * 100 if total else None)
    return hook


def _fetch_audio(info: dict, folder: Path, step=None) -> Path:
    """Lädt die Audiospur einmal in den Zwischenspeicher (für Vorschau-Player, Analyse und Schnitt)."""
    if audio := _audio_file(folder):
        return audio
    folder.mkdir(parents=True, exist_ok=True)
    opts = {
        "ignoreerrors": False,
        # m4a/webm spielen alle Browser ab
        "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
        "outtmpl": str(folder / "audio.%(ext)s"),
        "writethumbnail": True,
        "concurrent_fragment_downloads": 4,
        "progress_hooks": [_download_hook(step)] if step else [],
    }

    def run() -> None:
        with YoutubeDL({**_base_opts(), **opts}) as ydl:
            ydl.download([info["webpage_url"]])

    with_cookie_fallback(run)
    audio = _audio_file(folder)
    if not audio:
        raise RuntimeError("Audio konnte nicht geladen werden")
    return audio


def _envelope(folder: Path, audio: Path, step=None, duration: float | None = None) -> np.ndarray:
    path = folder / "envelope.npy"
    if path.exists():
        return np.load(path)
    on_progress = None
    if step and duration:
        on_progress = lambda sec: step.update(f"{int(sec // 60)} von {int(duration // 60)} Min.", sec / duration * 100)  # noqa: E731
    env = envelope(audio, on_progress)
    np.save(path, env)
    return env


def _comment_tracklist(url: str, duration: float) -> tuple[list[Segment], int]:
    info = with_cookie_fallback(lambda: _extract(
        url, getcomments=True, extractor_args={"youtube": {"max_comments": ["60"], "comment_sort": ["top"]}})) or {}
    comments = sorted(
        info.get("comments") or [],
        key=lambda c: (not c.get("is_pinned"), not c.get("author_is_uploader"), -(c.get("like_count") or 0)),
    )
    best: list[Segment] = []
    for comment in comments:
        segments = parse_tracklist(comment.get("text") or "", duration)
        if len(segments) > len(best):
            best = segments
    return best, len(comments)


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


def analyze(url: str, cfg: Config, activity: Activity | None = None) -> dict:
    """Findet Trackgrenzen und Titel. Reihenfolge: Kapitel → Beschreibung → Bild (OCR) → Kommentare → Pausen."""
    act = activity or NullActivity()
    cleanup_cache(cfg)

    step = act.step("Video-Infos laden")
    info = with_cookie_fallback(lambda: _extract(url))
    if not info:
        raise ValueError("Keine Informationen gefunden – ist die URL korrekt?")
    duration = float(info.get("duration") or 0)
    step.done(f"„{info.get('title') or ''}“ · {int(duration // 60)} Min.")

    folder = cache_dir(cfg, info["id"])
    cached = _audio_file(folder) is not None
    step = act.step("Audiospur laden")
    audio = _fetch_audio(info, folder, step)
    step.done(f"{'aus dem Zwischenspeicher' if cached else 'geladen'} · {_mb(audio.stat().st_size)} MB")

    cached = (folder / "envelope.npy").exists()
    step = act.step("Lautstärkeverlauf berechnen")
    env = _envelope(folder, audio, step, duration)
    duration = duration or len(env) / FPS
    step.done("aus dem Zwischenspeicher" if cached else f"{int(duration // 60)} Min. analysiert")

    hints: list[str] = []
    source = "stille"
    segments: list[Segment] = []

    step = act.step("YouTube-Kapitel")
    if len(info.get("chapters") or []) >= 2:
        source, segments = "kapitel", segments_from_chapters(info["chapters"], duration)
        step.done(f"{len(segments)} Kapitel gefunden")
    else:
        step.nothing("keine Kapitel")

    if segments:
        act.skip("Zeitstempel in der Beschreibung", "nicht nötig")
    else:
        step = act.step("Zeitstempel in der Beschreibung")
        description = info.get("description") or ""
        if segments := parse_tracklist(description, duration):
            source = "beschreibung"
            step.done(f"{len(segments)} Titel gefunden")
        else:
            step.nothing("Beschreibung ist leer" if not description.strip() else "keine Trackliste mit Zeitstempeln")

    if segments:
        act.skip("Trackliste im Videobild (OCR)", "nicht nötig")
    else:
        step = act.step("Trackliste im Videobild (OCR)", "Standbilder holen …")

        def ocr_progress(n: int, total: int, lines: int) -> None:
            step.update(f"Bild {n}/{total} gelesen" + (f" · {lines} Textzeilen" if lines else " · kein Text"),
                        n / total * 100)

        segments, hints = tracklist_from_frames(info, duration, on_progress=ocr_progress)
        if segments:
            source = "bild"
            step.done(f"{len(segments)} Titel mit Zeitstempeln im Bild gefunden")
        else:
            step.nothing("kein Text mit Zeitstempeln in den Standbildern")

    if segments:
        act.skip("Zeitstempel in Kommentaren", "nicht nötig")
    else:
        step = act.step("Zeitstempel in Kommentaren", "Kommentare laden …")
        segments, searched = _comment_tracklist(info["webpage_url"], duration)
        if segments:
            source = "kommentar"
            step.done(f"{len(segments)} Titel in einem von {searched} Kommentaren gefunden")
        else:
            step.nothing(f"{searched} Kommentare durchsucht, keine Trackliste")

    if segments and source != "kapitel":
        step = act.step("Grenzen auf Pausen ausrichten")
        segments = snap(segments, env)
        step.done("auf die leiseste Stelle in ±3 s gerückt")
    if not segments:
        step = act.step("Pausenerkennung im Audio")
        segments = segments_from_boundaries(detect_boundaries(env), duration)
        step.done(f"{len(segments) - 1} Pausen → {len(segments)} Titel – bitte besonders genau kontrollieren")

    base = music_item(info)
    artist = base.artist
    # Interpret im Bild (z.B. "DIRE STRAITS" über der Trackliste) ist meist zuverlässiger als der Videotitel
    if hints:
        big = [h for h in hints if len(h) > 3 and h.isupper()]
        if big:
            artist = big[0].title()
            act.step("Interpret im Bild erkannt").done(artist)

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
        "steps": act.log(),
    }


def redetect(cfg: Config, video_id: str, count: int | None, min_pause: float, sensitivity: float,
             artist: str, activity: Activity | None = None) -> dict:
    act = activity or NullActivity()
    folder = cache_dir(cfg, video_id)
    meta = load_meta(cfg, video_id)
    env = _envelope(folder, _audio_file(folder))
    step = act.step("Pausen suchen", f"genau {count} Titel" if count else
                    f"Pausen ab {min_pause:g} s, {sensitivity:g} dB unter dem Durchschnitt")
    cuts = detect_boundaries(env, count=count, min_pause=min_pause, sensitivity_db=sensitivity)
    segments = segments_from_boundaries(cuts, meta["duration"])
    if count and len(segments) < count:
        step.done(f"nur {len(segments)} von {count} Titeln möglich (Titel müssen mind. 30 s lang sein)")
    elif not cuts:
        step.nothing("keine Pausen gefunden – Empfindlichkeit verringern oder Anzahl Titel angeben")
    else:
        step.done(f"{len(cuts)} Pausen → {len(segments)} Titel")
    return {"source": "stille", "source_label": SOURCE_LABELS["stille"], "tracks": _tracks(segments, artist)}


def from_text(cfg: Config, video_id: str, text: str, artist: str, activity: Activity | None = None) -> dict:
    """Eingefügte Trackliste: mit Zeitstempeln → direkt übernehmen; nur Titel → so viele Grenzen suchen."""
    act = activity or NullActivity()
    folder = cache_dir(cfg, video_id)
    meta = load_meta(cfg, video_id)
    env = _envelope(folder, _audio_file(folder))
    step = act.step("Trackliste lesen")
    if segments := parse_tracklist(text, meta["duration"]):
        step.done(f"{len(segments)} Titel mit Zeitstempeln")
        step = act.step("Grenzen auf Pausen ausrichten")
        segments = snap(segments, env)
        step.done("auf die leiseste Stelle in ±3 s gerückt")
    else:
        titles = parse_titles(text)
        if not titles:
            raise ValueError("Keine Titel im Text gefunden")
        step.done(f"{len(titles)} Titel ohne Zeitstempel")
        step = act.step("Passende Pausen suchen", f"{len(titles) - 1} Grenzen")
        cuts = detect_boundaries(env, count=len(titles)) if len(titles) > 1 else []
        segments = segments_from_boundaries(cuts, meta["duration"])
        for seg, title in zip(segments, titles):
            seg.title = title
        step.done(f"{len(cuts)} Grenzen gefunden")
    return {"source": "eingabe", "source_label": SOURCE_LABELS["eingabe"], "tracks": _tracks(segments, artist)}


def scan_overlays(cfg: Config, video_id: str, artist: str, activity: Activity | None = None) -> dict:
    """Langsamer Bild-Scan: Video in 480p laden und alle 10 s die Einblendung lesen."""
    act = activity or NullActivity()
    folder = cache_dir(cfg, video_id)
    meta = load_meta(cfg, video_id)
    step = act.step("Video in 480p laden")
    video = next((p for p in folder.glob("video.*") if not p.name.endswith((".part", ".ytdl"))), None)
    if video:
        step.done("aus dem Zwischenspeicher")
    else:
        opts = {"ignoreerrors": False, "format": "bv*[height<=480]/b[height<=480]",
                "outtmpl": str(folder / "video.%(ext)s"), "concurrent_fragment_downloads": 4,
                "progress_hooks": [_download_hook(step)]}

        def run() -> None:
            with YoutubeDL({**_base_opts(), **opts}) as ydl:
                ydl.download([meta["url"]])

        with_cookie_fallback(run)
        video = next((p for p in folder.glob("video.*") if not p.name.endswith((".part", ".ytdl"))), None)
        if not video:
            raise RuntimeError("Video konnte nicht geladen werden")
        step.done(f"{_mb(video.stat().st_size)} MB")
    step = act.step("Einblendungen lesen (alle 10 s ein Bild)")
    segments = overlay_titles(video, meta["duration"],
                              on_progress=lambda n, total: step.update(f"Bild {n}/{total}", n / total * 100))
    if not segments:
        step.nothing("keine wechselnden Titeleinblendungen gefunden")
        raise ValueError("Keine wechselnden Titeleinblendungen gefunden")
    step.done(f"{len(segments)} verschiedene Einblendungen")
    step = act.step("Grenzen auf Pausen ausrichten")
    env = _envelope(folder, _audio_file(folder))
    segments = snap(segments, env, window=8.0)
    step.done("auf die leiseste Stelle in ±8 s gerückt")
    return {"source": "einblendung", "source_label": SOURCE_LABELS["einblendung"], "tracks": _tracks(segments, artist)}


def audio_path(cfg: Config, video_id: str) -> Path | None:
    return _audio_file(cache_dir(cfg, video_id))


def build_items(cfg: Config, video_id: str, album: str, album_artist: str, year: str, genre: str,
                tracks: list[dict], fmt: str = "", cover_url: str = "", cover_crop: bool = False,
                boundary_source: str = "") -> list[Item]:
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
            audio_format=fmt, on_conflict=track.get("on_conflict") or "keep_both",
            cover_url=cover_url.strip(), cover_crop=cover_crop, boundary_source=boundary_source,
            source_title=meta.get("title", ""),
        ))
    return items


def cut_track(item: Item, cfg: Config, progress: ProgressCallback) -> Path:
    """Schneidet einen Titel aus dem zwischengespeicherten Audio, taggt und legt ihn ab."""
    folder = cache_dir(cfg, item.source_id)
    audio = _audio_file(folder)
    if not audio:
        raise RuntimeError("Zwischengespeichertes Audio fehlt – bitte Video erneut analysieren")
    thumb = _thumbnail_file(folder)
    progress(Status.CUTTING, 10.0)
    with tempfile.TemporaryDirectory(prefix="ytdl-") as tmp:
        out = Path(tmp) / f"track.{audio_format(item, cfg)}"
        cut(audio, item.start or 0.0, item.end, out, cfg.bitrate)
        progress(Status.TAGGING, 90.0)
        cover, crop = choose_cover(item, cfg, thumb, progress)
        write_tags(out, item, cover, crop)
        target = place(out, item, cfg)
    Archive(cfg.data_dir, MUSIK).add(item.source_id)
    progress(Status.DONE, 100.0)
    return target
