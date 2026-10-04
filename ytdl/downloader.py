"""Download eines Titels in zwei Stufen (laden, dann umwandeln/taggen/ablegen) und das Prüfen einer URL."""

from __future__ import annotations

import argparse
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import ffmpeg, i18n
from .activity import Activity, NullActivity
from .auth import is_bot_check, youtube
from .config import Config, load_config
from .i18n import t
from .library import Archive, ProgressCallback, Skipped, audio_format, downloaded_file, finish_track, no_progress
from .metadata import MUSIK, PODCAST, Item, apply_playlist, music_item, podcast_item
from .split import encode
from .status import Status
from .ytdlp import download as ytdlp_download, extract_info

ALBUM_VIDEO_MIN_DURATION = 20 * 60  # Sekunden
PROBE_WORKERS = 4  # Playlist-Einträge gleichzeitig abfragen


def is_album_video(info: dict) -> bool:
    """Einzelvideo, das vermutlich ein ganzes Album enthält (Kapitel oder sehr lang)."""
    return info.get("_type") != "playlist" and (
        len(info.get("chapters") or []) >= 3 or (info.get("duration") or 0) >= ALBUM_VIDEO_MIN_DURATION
    )


def _entry_url(entry: dict) -> str:
    url = entry.get("url") or entry.get("webpage_url") or ""
    if url.startswith("http"):
        return url
    return f"https://www.youtube.com/watch?v={entry.get('id')}"


def probe(url: str, mode: str, cfg: Config, activity: Activity | None = None) -> dict:
    """Lädt nur die Metadaten (Einzelvideo oder alle Playlist-Einträge) – Schritte landen im Protokoll."""
    act = activity or NullActivity()
    step = act.step(t("steps.video_info"))
    info = extract_info(url, extract_flat="in_playlist")
    if not info:
        raise ValueError(t("errors.no_info_video"))

    is_playlist = info.get("_type") == "playlist"
    if is_playlist:
        flat = [e for e in (info.get("entries") or []) if e]
        step.done(t("steps.playlist", title=info.get("title") or "", count=len(flat)))
        details = act.step(t("steps.details"), f"0/{len(flat)}")
        entries: list[dict | None] = [None] * len(flat)
        finished = 0

        bot_errors: list[str] = []

        def load(index: int) -> None:
            try:
                entries[index] = extract_info(_entry_url(flat[index]))
            except Exception as exc:  # noqa: BLE001 – einzelner Titel nicht verfügbar → überspringen; Bot-Prüfung → abbrechen
                if is_bot_check(str(exc)):
                    bot_errors.append(str(exc))

        with ThreadPoolExecutor(max_workers=PROBE_WORKERS) as pool:
            for _ in as_completed(pool.submit(load, i) for i in range(len(flat))):
                finished += 1
                details.update(f"{finished}/{len(flat)}", finished / max(1, len(flat)) * 100)
        if bot_errors:
            raise RuntimeError(bot_errors[0])
        missing = sum(e is None for e in entries)
        entries = [e for e in entries if e]
        details.done(t("steps.details_done", count=len(entries))
                     + (f", {t('steps.details_missing', count=missing)}" if missing else ""))
    else:
        entries = [info]
        step.done(t("steps.video_title", title=info.get("title") or "", minutes=int(info.get("duration") or 0) // 60))

    make = music_item if mode == MUSIK else podcast_item
    items = [make(e) for e in entries]
    if is_playlist and mode == MUSIK:
        apply_playlist(items, info)
        if items and items[0].album:
            act.step(t("steps.album_detected")).done(t("steps.album_by", album=items[0].album,
                                                       artist=items[0].album_artist))

    archive = act.step(t("steps.archive"))
    done = Archive(cfg.data_dir, mode).ids()
    already = sum(i.id in done for i in items)
    archive.done(t("steps.archive_already", count=already) if already else t("steps.archive_new"))
    return {
        "title": info.get("title") or "",
        "is_playlist": is_playlist,
        "album_video": mode == MUSIK and is_album_video(info),
        "items": [{**i.to_dict(), "already": i.id in done} for i in items],
    }


def work_dir(cfg: Config, item: Item) -> Path:
    return cfg.data_dir / "work" / f"{item.mode}-{item.id}"


def fetch(item: Item, cfg: Config, progress: ProgressCallback | None = None, workdir: Path | None = None) -> Path:
    """Stufe 1 (Netzwerk): Audiospur + Vorschaubild in ein Arbeitsverzeichnis laden. Gibt das Verzeichnis zurück."""
    report = progress or no_progress
    folder = work_dir(cfg, item)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    extra = {
        "writethumbnail": True,
        "retry_sleep_functions": {"http": lambda n: min(30, 2 ** n), "fragment": lambda n: min(30, 2 ** n)},
    }
    if youtube.sleep:  # Pause vor dem Download (zufällig n…2n s), um YouTube nicht zu viele Anfragen zu schicken
        extra.update(sleep_interval=youtube.sleep, max_sleep_interval=youtube.sleep * 2)
    report(Status.DOWNLOADING, 0.0)
    # für M4A gleich die AAC-Spur nehmen – dann wird nur umverpackt, nicht neu kodiert
    fmt = "bestaudio[ext=m4a]/bestaudio/best" if audio_format(item, cfg) == "m4a" else "bestaudio/best"
    try:
        ytdlp_download(item.url or item.id, folder / "source.%(ext)s", fmt,
                       lambda detail, pct: report(Status.DOWNLOADING, pct or 0.0, detail), **extra)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return folder


def convert(item: Item, cfg: Config, progress: ProgressCallback | None, workdir: Path) -> Path:
    """Stufe 2 (CPU): umwandeln (ffmpeg), taggen, ablegen, Arbeitsverzeichnis aufräumen. Bei anderen Fehlern bleibt
    das Arbeitsverzeichnis, damit ein neuer Versuch nicht erneut laden muss."""
    report = progress or no_progress
    fmt = audio_format(item, cfg)
    source = downloaded_file(workdir, "source")
    if source is None:
        raise RuntimeError(t("errors.download_missing"))
    try:
        report(Status.CONVERTING, 0.0, f"{source.suffix.lstrip('.').upper()} → {fmt.upper()}")
        out = workdir / f"out.{fmt}"
        encode(source, out, cfg.bitrate)
        target = finish_track(out, item, cfg, downloaded_file(workdir, "source", image=True), report, 80.0)
    except Skipped:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    shutil.rmtree(workdir, ignore_errors=True)
    return target


def download(item: Item, cfg: Config, progress: ProgressCallback | None = None) -> Path:
    """Beide Stufen nacheinander (für die Kommandozeile)."""
    return convert(item, cfg, progress, fetch(item, cfg, progress))


def main() -> None:
    """Kleiner Kommandozeilen-Test: python -m ytdl.downloader <url> --mode musik"""
    parser = argparse.ArgumentParser(description="YouTube → MP3 (Test ohne Weboberfläche)")
    parser.add_argument("url")
    parser.add_argument("--mode", choices=[MUSIK, PODCAST], default=MUSIK)
    parser.add_argument("--probe", action="store_true", help="nur Metadaten anzeigen")
    args = parser.parse_args()

    cfg = load_config()
    ffmpeg.configure(cfg.ffmpeg_location)
    i18n.configure(cfg.language)
    youtube.configure(cfg)
    result = probe(args.url, args.mode, cfg)
    for data in result["items"]:
        item = Item.from_dict(data)
        print(f"{item.artist} - {item.title}  [{item.album or '-'}]  ← {item.source_title}")
        if not args.probe:
            path = download(item, cfg, lambda s, p: print(f"  {s} {p:5.1f}%", end="\r"))
            print(f"\n  → {path}")


if __name__ == "__main__":
    main()
