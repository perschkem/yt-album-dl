"""Album in einem Video: analysieren (Grenzen + Titel finden) und in getaggte Einzeltitel schneiden."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import numpy as np

from .activity import Activity, NullActivity, Step
from .config import Config
from .library import ProgressCallback, audio_format, downloaded_file, finish_track
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
from .ytdlp import download as ytdlp_download, extract_info, mb

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
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


# ---------- Zwischenspeicher ----------

class AlbumCache:
    """Zwischenspeicher eines Videos unter data/cache/<video-id>/: Audiospur (für Vorschau-Player, Analyse und
    Schnitt) samt Vorschaubild, 480p-Video für den Einblendungs-Scan, Lautstärkeverlauf und die Analyse-Metadaten."""

    def __init__(self, cfg: Config, video_id: str):
        if not _VIDEO_ID.fullmatch(video_id):
            raise ValueError("Ungültige Video-ID")
        self.video_id = video_id
        self.folder = cfg.data_dir / "cache" / video_id

    @staticmethod
    def cleanup(cfg: Config) -> None:
        """Zwischenspeicher, die länger als CACHE_DAYS nicht angefasst wurden, löschen."""
        root = cfg.data_dir / "cache"
        if not root.exists():
            return
        limit = time.time() - CACHE_DAYS * 86400
        for entry in root.iterdir():
            if entry.is_dir() and entry.stat().st_mtime < limit:
                shutil.rmtree(entry, ignore_errors=True)

    @property
    def audio(self) -> Path | None:
        """Die Audiospur – nicht das gleichnamige Vorschaubild (audio.webp/.jpg)."""
        return downloaded_file(self.folder, "audio")

    @property
    def thumbnail(self) -> Path | None:
        return downloaded_file(self.folder, "audio", image=True)

    @property
    def video(self) -> Path | None:
        return downloaded_file(self.folder, "video")

    def require_audio(self) -> Path:
        if audio := self.audio:
            return audio
        raise RuntimeError("Zwischengespeichertes Audio fehlt – bitte Video erneut analysieren")

    def fetch_audio(self, url: str, step: Step | None = None) -> Path:
        """Lädt die Audiospur einmal (m4a/webm spielen alle Browser ab)."""
        if audio := self.audio:
            return audio
        self.folder.mkdir(parents=True, exist_ok=True)
        ytdlp_download(url, self.folder / "audio.%(ext)s", "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
                       step.update if step else None, writethumbnail=True)
        if audio := self.audio:
            return audio
        raise RuntimeError("Audio konnte nicht geladen werden")

    def fetch_video(self, url: str, step: Step | None = None) -> Path:
        """Lädt das Video in 480p (nur für das Lesen der Einblendungen)."""
        if video := self.video:
            return video
        ytdlp_download(url, self.folder / "video.%(ext)s", "bv*[height<=480]/b[height<=480]",
                       step.update if step else None)
        if video := self.video:
            return video
        raise RuntimeError("Video konnte nicht geladen werden")

    @property
    def _envelope_path(self) -> Path:
        return self.folder / "envelope.npy"

    @property
    def has_envelope(self) -> bool:
        return self._envelope_path.exists()

    def envelope(self, step: Step | None = None, duration: float | None = None) -> np.ndarray:
        """Lautstärkeverlauf – einmal berechnen, danach aus dem Zwischenspeicher."""
        if self.has_envelope:
            return np.load(self._envelope_path)
        on_progress = None
        if step and duration:
            def on_progress(sec: float) -> None:
                step.update(f"{int(sec // 60)} von {int(duration // 60)} Min.", sec / duration * 100)
        env = envelope(self.require_audio(), on_progress)
        np.save(self._envelope_path, env)
        return env

    def save_meta(self, meta: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def meta(self) -> dict:
        path = self.folder / "meta.json"
        if not path.exists():
            raise ValueError("Video nicht analysiert – bitte erneut prüfen")
        return json.loads(path.read_text(encoding="utf-8"))


def audio_path(cfg: Config, video_id: str) -> Path | None:
    return AlbumCache(cfg, video_id).audio


# ---------- Hilfen ----------

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


def _result(source: str, segments: list[Segment], artist: str) -> dict:
    """Ergebnis einer Erkennung für die Oberfläche: Quelle + Trackzeilen."""
    return {"source": source, "source_label": SOURCE_LABELS[source], "tracks": _tracks(segments, artist)}


def _snap_step(act: Activity, segments: list[Segment], env: np.ndarray, window: float = 3.0) -> list[Segment]:
    step = act.step("Grenzen auf Pausen ausrichten")
    segments = snap(segments, env, window=window)
    step.done(f"auf die leiseste Stelle in ±{window:g} s gerückt")
    return segments


# ---------- Quellen für Trackgrenzen (in dieser Reihenfolge versucht) ----------

class Found(NamedTuple):
    segments: list[Segment]
    message: str  # Text für den Schritt – „gefunden“ oder „nichts gefunden“
    hints: tuple[str, ...] = ()  # übrige Textzeilen im Bild (z.B. der Interpret)


def _from_chapters(info: dict, duration: float, step: Step) -> Found:
    if len(info.get("chapters") or []) >= 2:
        segments = segments_from_chapters(info["chapters"], duration)
        return Found(segments, f"{len(segments)} Kapitel gefunden")
    return Found([], "keine Kapitel")


def _from_description(info: dict, duration: float, step: Step) -> Found:
    description = info.get("description") or ""
    if segments := parse_tracklist(description, duration):
        return Found(segments, f"{len(segments)} Titel gefunden")
    return Found([], "Beschreibung ist leer" if not description.strip() else "keine Trackliste mit Zeitstempeln")


def _from_frames(info: dict, duration: float, step: Step) -> Found:
    def on_progress(n: int, total: int, lines: int) -> None:
        step.update(f"Bild {n}/{total} gelesen" + (f" · {lines} Textzeilen" if lines else " · kein Text"),
                    n / total * 100)

    segments, hints = tracklist_from_frames(info, duration, on_progress=on_progress)
    if segments:
        return Found(segments, f"{len(segments)} Titel mit Zeitstempeln im Bild gefunden", tuple(hints))
    return Found([], "kein Text mit Zeitstempeln in den Standbildern", tuple(hints))


def _from_comments(info: dict, duration: float, step: Step) -> Found:
    info = extract_info(info["webpage_url"], getcomments=True,
                        extractor_args={"youtube": {"max_comments": ["60"], "comment_sort": ["top"]}}) or {}
    comments = sorted(
        info.get("comments") or [],
        key=lambda c: (not c.get("is_pinned"), not c.get("author_is_uploader"), -(c.get("like_count") or 0)),
    )
    best: list[Segment] = []
    for comment in comments:
        segments = parse_tracklist(comment.get("text") or "", duration)
        if len(segments) > len(best):
            best = segments
    if best:
        return Found(best, f"{len(best)} Titel in einem von {len(comments)} Kommentaren gefunden")
    return Found([], f"{len(comments)} Kommentare durchsucht, keine Trackliste")


Finder = Callable[[dict, float, Step], Found]
# (Quelle, Schritt, Text beim Start, Suche)
SOURCES: list[tuple[str, str, str, Finder]] = [
    ("kapitel", "YouTube-Kapitel", "", _from_chapters),
    ("beschreibung", "Zeitstempel in der Beschreibung", "", _from_description),
    ("bild", "Trackliste im Videobild (OCR)", "Standbilder holen …", _from_frames),
    ("kommentar", "Zeitstempel in Kommentaren", "Kommentare laden …", _from_comments),
]


def _find_segments(act: Activity, info: dict, duration: float) -> tuple[str, list[Segment], list[str]]:
    """Probiert die Quellen der Reihe nach; nach dem ersten Treffer werden die übrigen übersprungen."""
    hints: list[str] = []
    for i, (source, label, detail, find) in enumerate(SOURCES):
        step = act.step(label, detail)
        found = find(info, duration, step)
        hints = hints or list(found.hints)
        if found.segments:
            step.done(found.message)
            for _, later, _, _ in SOURCES[i + 1:]:
                act.skip(later, "nicht nötig")
            return source, found.segments, hints
        step.nothing(found.message)
    return "stille", [], hints


# ---------- Vorgänge ----------

def analyze(url: str, cfg: Config, activity: Activity | None = None) -> dict:
    """Findet Trackgrenzen und Titel. Reihenfolge: Kapitel → Beschreibung → Bild (OCR) → Kommentare → Pausen."""
    act = activity or NullActivity()
    AlbumCache.cleanup(cfg)

    step = act.step("Video-Infos laden")
    info = extract_info(url)
    if not info:
        raise ValueError("Keine Informationen gefunden – ist die URL korrekt?")
    duration = float(info.get("duration") or 0)
    step.done(f"„{info.get('title') or ''}“ · {int(duration // 60)} Min.")

    cache = AlbumCache(cfg, info["id"])
    cached = cache.audio is not None
    step = act.step("Audiospur laden")
    audio = cache.fetch_audio(info["webpage_url"], step)
    step.done(f"{'aus dem Zwischenspeicher' if cached else 'geladen'} · {mb(audio.stat().st_size)} MB")

    cached = cache.has_envelope
    step = act.step("Lautstärkeverlauf berechnen")
    env = cache.envelope(step, duration)
    duration = duration or len(env) / FPS
    step.done("aus dem Zwischenspeicher" if cached else f"{int(duration // 60)} Min. analysiert")

    source, segments, hints = _find_segments(act, info, duration)
    if segments and source != "kapitel":
        segments = _snap_step(act, segments, env)
    if not segments:
        step = act.step("Pausenerkennung im Audio")
        segments = segments_from_boundaries(detect_boundaries(env), duration)
        step.done(f"{len(segments) - 1} Pausen → {len(segments)} Titel – bitte besonders genau kontrollieren")

    base = music_item(info)
    artist = base.artist
    # Interpret im Bild (z.B. "DIRE STRAITS" über der Trackliste) ist meist zuverlässiger als der Videotitel
    if big := [h for h in hints if len(h) > 3 and h.isupper()]:
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
    cache.save_meta(meta)
    return {
        **meta,
        **_result(source, segments, artist),
        "artist": artist,
        "album": _guess_album(meta["title"]),
        "hints": hints,
        "peaks": peaks(env),
        "audio_url": f"/api/album/{info['id']}/audio",
        "steps": act.log(),
    }


def redetect(cfg: Config, video_id: str, count: int | None, min_pause: float, sensitivity: float,
             artist: str, activity: Activity | None = None) -> dict:
    act = activity or NullActivity()
    cache = AlbumCache(cfg, video_id)
    meta, env = cache.meta(), cache.envelope()
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
    return _result("stille", segments, artist)


def from_text(cfg: Config, video_id: str, text: str, artist: str, activity: Activity | None = None) -> dict:
    """Eingefügte Trackliste: mit Zeitstempeln → direkt übernehmen; nur Titel → so viele Grenzen suchen."""
    act = activity or NullActivity()
    cache = AlbumCache(cfg, video_id)
    meta, env = cache.meta(), cache.envelope()
    step = act.step("Trackliste lesen")
    if segments := parse_tracklist(text, meta["duration"]):
        step.done(f"{len(segments)} Titel mit Zeitstempeln")
        segments = _snap_step(act, segments, env)
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
    return _result("eingabe", segments, artist)


def scan_overlays(cfg: Config, video_id: str, artist: str, activity: Activity | None = None) -> dict:
    """Langsamer Bild-Scan: Video in 480p laden und alle 10 s die Einblendung lesen."""
    act = activity or NullActivity()
    cache = AlbumCache(cfg, video_id)
    meta = cache.meta()
    step = act.step("Video in 480p laden")
    cached = cache.video is not None
    video = cache.fetch_video(meta["url"], step)
    step.done("aus dem Zwischenspeicher" if cached else f"{mb(video.stat().st_size)} MB")
    step = act.step("Einblendungen lesen (alle 10 s ein Bild)")
    segments = overlay_titles(video, meta["duration"],
                              on_progress=lambda n, total: step.update(f"Bild {n}/{total}", n / total * 100))
    if not segments:
        step.nothing("keine wechselnden Titeleinblendungen gefunden")
        raise ValueError("Keine wechselnden Titeleinblendungen gefunden")
    step.done(f"{len(segments)} verschiedene Einblendungen")
    segments = _snap_step(act, segments, cache.envelope(), window=8.0)
    return _result("einblendung", segments, artist)


# ---------- Schneiden ----------

def build_items(cfg: Config, video_id: str, album: str, album_artist: str, year: str, genre: str,
                tracks: list[dict], fmt: str = "", cover_url: str = "", cover_crop: bool = False,
                boundary_source: str = "") -> list[Item]:
    meta = AlbumCache(cfg, video_id).meta()
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


def cut_track(item: Item, cfg: Config, progress: ProgressCallback, workdir: Path | None = None) -> Path:
    """Schneidet einen Titel aus dem zwischengespeicherten Audio, taggt und legt ihn ab."""
    cache = AlbumCache(cfg, item.source_id)
    audio = cache.require_audio()
    progress(Status.CUTTING, 10.0)
    with tempfile.TemporaryDirectory(prefix="ytdl-") as tmp:
        out = Path(tmp) / f"track.{audio_format(item, cfg)}"
        cut(audio, item.start or 0.0, item.end, out, cfg.bitrate)
        return finish_track(out, item, cfg, cache.thumbnail, progress, 90.0)
