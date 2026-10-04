"""yt-dlp-Anbindung: Metadaten abfragen, herunterladen, zu MP3 konvertieren, taggen, ablegen."""

from __future__ import annotations

import argparse
import shutil
import tempfile
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from yt_dlp import YoutubeDL

from .activity import Activity, NullActivity

from .config import Config, load_config
from .metadata import MUSIK, PODCAST, Item, apply_playlist, music_item, podcast_item
from .paths import target_path
from .tagger import write_tags

ProgressCallback = Callable[..., None]  # (Status, Prozent 0..100, Detailtext="")
ALBUM_VIDEO_MIN_DURATION = 20 * 60  # Sekunden
PROBE_WORKERS = 4  # Playlist-Einträge gleichzeitig abfragen


def ffmpeg_available(cfg: Config) -> bool:
    if cfg.ffmpeg_location:
        return (Path(cfg.ffmpeg_location) / "ffmpeg").exists() or Path(cfg.ffmpeg_location).is_file()
    return shutil.which("ffmpeg") is not None


class Archive:
    """Merkt sich bereits heruntergeladene Video-IDs je Modus (data/archive-<modus>.txt)."""

    def __init__(self, data_dir: Path, mode: str):
        self.path = data_dir / f"archive-{mode}.txt"
        self._lock = threading.Lock()

    def ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        return {line.strip() for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()}

    def add(self, video_id: str) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(video_id + "\n")


def _base_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        # Bei einer Video-URL mit &list=... (z.B. aus einem Mix) nur das Video nehmen.
        # Reine Playlist-URLs (…/playlist?list=…) werden trotzdem komplett geladen.
        "noplaylist": True,
        "ignoreerrors": True,
    }
    # yt-dlp braucht für YouTube eine JavaScript-Umgebung; standardmäßig sucht es nur deno
    if shutil.which("deno") is None and (node := shutil.which("node")):
        opts["js_runtimes"] = {"node": {"path": node}}
    return opts


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
    step = act.step("Video-Infos laden")
    with YoutubeDL({**_base_opts(), "extract_flat": "in_playlist"}) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise ValueError("Keine Informationen gefunden – ist die URL korrekt und das Video verfügbar?")

    is_playlist = info.get("_type") == "playlist"
    if is_playlist:
        flat = [e for e in (info.get("entries") or []) if e]
        step.done(f"Playlist „{info.get('title') or ''}“ mit {len(flat)} Einträgen")
        details = act.step("Details der Titel laden", f"0/{len(flat)}")
        entries: list[dict | None] = [None] * len(flat)
        finished = 0

        def load(index: int) -> None:
            with YoutubeDL(_base_opts()) as y:
                entries[index] = y.extract_info(_entry_url(flat[index]), download=False)

        with ThreadPoolExecutor(max_workers=PROBE_WORKERS) as pool:
            for _ in as_completed(pool.submit(load, i) for i in range(len(flat))):
                finished += 1
                details.update(f"{finished}/{len(flat)}", finished / max(1, len(flat)) * 100)
        missing = sum(e is None for e in entries)
        entries = [e for e in entries if e]
        details.done(f"{len(entries)} Titel" + (f", {missing} nicht verfügbar" if missing else ""))
    else:
        entries = [info]
        length = f" · {int(info['duration']) // 60} Min." if info.get("duration") else ""
        step.done(f"„{info.get('title') or ''}“{length}")

    make = music_item if mode == MUSIK else podcast_item
    items = [make(e) for e in entries]
    if is_playlist and mode == MUSIK:
        apply_playlist(items, info)
        if items and items[0].album:
            act.step("Album erkannt").done(f"„{items[0].album}“ von {items[0].album_artist}")

    archive = act.step("Mit bereits geladenen Titeln abgleichen")
    done = Archive(cfg.data_dir, mode).ids()
    already = sum(i.id in done for i in items)
    archive.done(f"{already} bereits geladen" if already else "alles neu")
    return {
        "title": info.get("title") or "",
        "is_playlist": is_playlist,
        "album_video": mode == MUSIK and is_album_video(info),
        "items": [{**i.to_dict(), "already": i.id in done} for i in items],
    }


def _unique(path: Path) -> Path:
    """Hängt ' (2)', ' (3)' … an, falls die Datei schon existiert – es wird nie etwas überschrieben."""
    if not path.exists():
        return path
    n = 2
    while (candidate := path.with_name(f"{path.stem} ({n}){path.suffix}")).exists():
        n += 1
    return candidate


_PLACE_LOCK = threading.Lock()


def place(src: Path, item: Item, cfg: Config, suffix: str = ".mp3") -> Path:
    """Verschiebt die fertige Datei an ihren Zielort. Gesperrt, damit parallele Titel mit gleichem
    Namen nicht beide denselben freien Dateinamen wählen."""
    target = target_path(item, cfg.musik_dir, cfg.podcast_dir).with_suffix(suffix)
    with _PLACE_LOCK:
        target = _unique(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), target)
    return target


def _mb(value: float | None) -> str:
    return f"{(value or 0) / 1_048_576:.1f}"


def download(item: Item, cfg: Config, progress: ProgressCallback | None = None) -> Path:
    """Lädt einen Titel herunter, konvertiert zu MP3/M4A, schreibt Tags und verschiebt ihn in den Zielordner."""
    fmt = cfg.audio_format
    report = progress or (lambda status, pct, detail="": None)

    def on_download(d: dict) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            detail = f"{_mb(done)} von {_mb(total)} MB" if total else f"{_mb(done)} MB"
            if d.get("speed"):
                detail += f" · {_mb(d['speed'])} MB/s"
            report("lädt", min(90.0, done / total * 90) if total else 0.0, detail)
        elif d["status"] == "finished":
            report("konvertiert", 90.0, f"zu {cfg.audio_format.upper()}")

    with tempfile.TemporaryDirectory(prefix="ytdl-") as tmp:
        tmp_dir = Path(tmp)
        opts = {
            **_base_opts(),
            "ignoreerrors": False,
            # für M4A gleich die AAC-Spur nehmen – dann wird nur umverpackt, nicht neu kodiert
            "format": "bestaudio[ext=m4a]/bestaudio/best" if fmt == "m4a" else "bestaudio/best",
            "outtmpl": str(tmp_dir / "%(id)s.%(ext)s"),
            "writethumbnail": True,
            "concurrent_fragment_downloads": 4,
            "retry_sleep_functions": {"http": lambda n: min(30, 2 ** n), "fragment": lambda n: min(30, 2 ** n)},
            "progress_hooks": [on_download],
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": fmt, "preferredquality": str(cfg.bitrate)}
            ],
        }
        if cfg.ffmpeg_location:
            opts["ffmpeg_location"] = cfg.ffmpeg_location

        report("lädt", 0.0)
        with YoutubeDL(opts) as ydl:
            ydl.download([item.url or item.id])

        mp3s = list(tmp_dir.glob(f"*.{fmt}"))
        if not mp3s:
            raise RuntimeError(f"Konvertierung zu {fmt.upper()} fehlgeschlagen (ist ffmpeg installiert?)")
        thumbs = [p for p in tmp_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]

        report("taggt", 95.0)
        write_tags(mp3s[0], item, thumbs[0] if thumbs else None)

        target = place(mp3s[0], item, cfg, f".{fmt}")

    Archive(cfg.data_dir, item.mode).add(item.id)
    report("fertig", 100.0)
    return target


def main() -> None:
    """Kleiner Kommandozeilen-Test: python -m ytdl.downloader <url> --mode musik"""
    parser = argparse.ArgumentParser(description="YouTube → MP3 (Test ohne Weboberfläche)")
    parser.add_argument("url")
    parser.add_argument("--mode", choices=[MUSIK, PODCAST], default=MUSIK)
    parser.add_argument("--probe", action="store_true", help="nur Metadaten anzeigen")
    args = parser.parse_args()

    cfg = load_config()
    result = probe(args.url, args.mode, cfg)
    for data in result["items"]:
        item = Item.from_dict(data)
        print(f"{item.artist} - {item.title}  [{item.album or '-'}]  ← {item.source_title}")
        if not args.probe:
            path = download(item, cfg, lambda s, p: print(f"  {s} {p:5.1f}%", end="\r"))
            print(f"\n  → {path}")


if __name__ == "__main__":
    main()
