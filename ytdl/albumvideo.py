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
from .errors import InvalidVideoId, PermanentError
from .i18n import t
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
# Woher die Trackgrenzen stammen – Codes (auch in der Historie), angezeigt als source.<code>
CHAPTERS, DESCRIPTION, IMAGE, COMMENT = "chapters", "description", "image", "comment"
OVERLAY, TEXT, SILENCE = "overlay", "text", "silence"
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
            raise InvalidVideoId(t("errors.invalid_video_id"))
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
        raise PermanentError(t("errors.cached_audio_missing"))

    def fetch_audio(self, url: str, step: Step | None = None) -> Path:
        """Lädt die Audiospur einmal (m4a/webm spielen alle Browser ab)."""
        if audio := self.audio:
            return audio
        self.folder.mkdir(parents=True, exist_ok=True)
        ytdlp_download(url, self.folder / "audio.%(ext)s", "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio",
                       step.update if step else None, writethumbnail=True)
        if audio := self.audio:
            return audio
        raise RuntimeError(t("errors.audio_download_failed"))

    def fetch_video(self, url: str, step: Step | None = None) -> Path:
        """Lädt das Video in 480p (nur für das Lesen der Einblendungen)."""
        if video := self.video:
            return video
        ytdlp_download(url, self.folder / "video.%(ext)s", "bv*[height<=480]/b[height<=480]",
                       step.update if step else None)
        if video := self.video:
            return video
        raise RuntimeError(t("errors.video_download_failed"))

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
                step.update(t("progress.minutes_of", done=int(sec // 60), total=int(duration // 60)), sec / duration * 100)
        env = envelope(self.require_audio(), on_progress)
        np.save(self._envelope_path, env)
        return env

    def save_meta(self, meta: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def meta(self) -> dict:
        path = self.folder / "meta.json"
        if not path.exists():
            raise ValueError(t("errors.not_analyzed"))
        return json.loads(path.read_text(encoding="utf-8"))


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
    return {"source": source, "source_label": t(f"source.{source}"), "tracks": _tracks(segments, artist)}


def _snap_step(act: Activity, segments: list[Segment], env: np.ndarray, window: float = 3.0) -> list[Segment]:
    step = act.step(t("steps.snap"))
    segments = snap(segments, env, window=window)
    step.done(t("steps.snap_done", seconds=f"{window:g}"))
    return segments


# ---------- Quellen für Trackgrenzen (in dieser Reihenfolge versucht) ----------

class Found(NamedTuple):
    segments: list[Segment]
    message: str  # Text für den Schritt – „gefunden“ oder „nichts gefunden“
    hints: tuple[str, ...] = ()  # übrige Textzeilen im Bild (z.B. der Interpret)


def _from_chapters(info: dict, duration: float, step: Step) -> Found:
    if len(info.get("chapters") or []) >= 2:
        segments = segments_from_chapters(info["chapters"], duration)
        return Found(segments, t("steps.chapters_found", count=len(segments)))
    return Found([], t("steps.no_chapters"))


def _from_description(info: dict, duration: float, step: Step) -> Found:
    description = info.get("description") or ""
    if segments := parse_tracklist(description, duration):
        return Found(segments, t("steps.titles_found", count=len(segments)))
    return Found([], t("steps.description_empty") if not description.strip() else t("steps.no_timestamps"))


def _from_frames(info: dict, duration: float, step: Step) -> Found:
    def on_progress(n: int, total: int, lines: int) -> None:
        found = t("steps.frame_lines", count=lines) if lines else t("steps.frame_no_text")
        step.update(f"{t('steps.frame_read', n=n, total=total)} · {found}", n / total * 100)

    segments, hints = tracklist_from_frames(info, duration, on_progress=on_progress)
    if segments:
        return Found(segments, t("steps.image_found", count=len(segments)), tuple(hints))
    return Found([], t("steps.image_nothing"), tuple(hints))


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
        return Found(best, t("steps.comments_found", count=len(best), comments=len(comments)))
    return Found([], t("steps.comments_nothing", count=len(comments)))


Finder = Callable[[dict, float, Step], Found]
# (Quelle, Schlüssel des Schritts, Schlüssel für den Text beim Start, Suche)
SOURCES: list[tuple[str, str, str, Finder]] = [
    (CHAPTERS, "steps.chapters", "", _from_chapters),
    (DESCRIPTION, "steps.description", "", _from_description),
    (IMAGE, "steps.image", "steps.image_start", _from_frames),
    (COMMENT, "steps.comments", "steps.comments_start", _from_comments),
]


def _find_segments(act: Activity, info: dict, duration: float) -> tuple[str, list[Segment], list[str]]:
    """Probiert die Quellen der Reihe nach; nach dem ersten Treffer werden die übrigen übersprungen."""
    hints: list[str] = []
    for i, (source, label, detail, find) in enumerate(SOURCES):
        step = act.step(t(label), t(detail) if detail else "")
        found = find(info, duration, step)
        hints = hints or list(found.hints)
        if found.segments:
            step.done(found.message)
            for _, later, _, _ in SOURCES[i + 1:]:
                act.skip(t(later), t("steps.not_needed"))
            return source, found.segments, hints
        step.nothing(found.message)
    return SILENCE, [], hints


# ---------- Vorgänge ----------

def analyze(url: str, cfg: Config, activity: Activity | None = None) -> dict:
    """Findet Trackgrenzen und Titel. Reihenfolge: Kapitel → Beschreibung → Bild (OCR) → Kommentare → Pausen."""
    act = activity or NullActivity()
    AlbumCache.cleanup(cfg)

    step = act.step(t("steps.video_info"))
    info = extract_info(url)
    if not info:
        raise ValueError(t("errors.no_info_url"))
    duration = float(info.get("duration") or 0)
    step.done(t("steps.video_title", title=info.get("title") or "", minutes=int(duration // 60)))

    cache = AlbumCache(cfg, info["id"])
    cached = cache.audio is not None
    step = act.step(t("steps.audio"))
    audio = cache.fetch_audio(info["webpage_url"], step)
    step.done(t("steps.audio_cached" if cached else "steps.audio_downloaded", mb=mb(audio.stat().st_size)))

    cached = cache.has_envelope
    step = act.step(t("steps.envelope"))
    env = cache.envelope(step, duration)
    duration = duration or len(env) / FPS
    step.done(t("steps.from_cache") if cached else t("steps.envelope_done", minutes=int(duration // 60)))

    source, segments, hints = _find_segments(act, info, duration)
    if segments and source != CHAPTERS:
        segments = _snap_step(act, segments, env)
    if not segments:
        step = act.step(t("steps.silence"))
        segments = segments_from_boundaries(detect_boundaries(env), duration)
        step.done(t("steps.silence_done", pauses=len(segments) - 1, count=len(segments)))

    base = music_item(info)
    artist = base.artist
    # Interpret im Bild (z.B. "DIRE STRAITS" über der Trackliste) ist meist zuverlässiger als der Videotitel
    if big := [h for h in hints if len(h) > 3 and h.isupper()]:
        artist = big[0].title()
        act.step(t("steps.artist_in_image")).done(artist)

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
    step = act.step(t("steps.find_pauses"), t("steps.find_pauses_count", count=count) if count else
                    t("steps.find_pauses_auto", seconds=f"{min_pause:g}", db=f"{sensitivity:g}"))
    cuts = detect_boundaries(env, count=count, min_pause=min_pause, sensitivity_db=sensitivity)
    segments = segments_from_boundaries(cuts, meta["duration"])
    if count and len(segments) < count:
        step.done(t("steps.pauses_too_few", found=len(segments), count=count))
    elif not cuts:
        step.nothing(t("steps.no_pauses"))
    else:
        step.done(t("steps.pauses_found", pauses=len(cuts), count=len(segments)))
    return _result(SILENCE, segments, artist)


def from_text(cfg: Config, video_id: str, text: str, artist: str, activity: Activity | None = None) -> dict:
    """Eingefügte Trackliste: mit Zeitstempeln → direkt übernehmen; nur Titel → so viele Grenzen suchen."""
    act = activity or NullActivity()
    cache = AlbumCache(cfg, video_id)
    meta, env = cache.meta(), cache.envelope()
    step = act.step(t("steps.read_tracklist"))
    if segments := parse_tracklist(text, meta["duration"]):
        step.done(t("steps.tracklist_timestamps", count=len(segments)))
        segments = _snap_step(act, segments, env)
    else:
        titles = parse_titles(text)
        if not titles:
            raise ValueError(t("errors.no_titles_in_text"))
        step.done(t("steps.tracklist_titles", count=len(titles)))
        step = act.step(t("steps.matching_pauses"), t("steps.boundaries", count=len(titles) - 1))
        cuts = detect_boundaries(env, count=len(titles)) if len(titles) > 1 else []
        segments = segments_from_boundaries(cuts, meta["duration"])
        for seg, title in zip(segments, titles):
            seg.title = title
        step.done(t("steps.boundaries_found", count=len(cuts)))
    return _result(TEXT, segments, artist)


def scan_overlays(cfg: Config, video_id: str, artist: str, activity: Activity | None = None) -> dict:
    """Langsamer Bild-Scan: Video in 480p laden und alle 10 s die Einblendung lesen."""
    act = activity or NullActivity()
    cache = AlbumCache(cfg, video_id)
    meta = cache.meta()
    step = act.step(t("steps.video_480"))
    cached = cache.video is not None
    video = cache.fetch_video(meta["url"], step)
    step.done(t("steps.from_cache") if cached else t("progress.mb", mb=mb(video.stat().st_size)))
    step = act.step(t("steps.read_overlays"))
    segments = overlay_titles(video, meta["duration"],
                              on_progress=lambda n, total: step.update(t("steps.frame", n=n, total=total), n / total * 100))
    if not segments:
        step.nothing(t("steps.no_overlays"))
        raise ValueError(t("errors.no_overlays"))
    step.done(t("steps.overlays_found", count=len(segments)))
    segments = _snap_step(act, segments, cache.envelope(), window=8.0)
    return _result(OVERLAY, segments, artist)


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
