"""yt-dlp-Aufrufe: gemeinsame Optionen, Infos abfragen, herunterladen – jeweils mit Cookie-Fallback."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from yt_dlp import YoutubeDL

from . import ffmpeg
from .auth import youtube
from .i18n import t

ProgressText = Callable[[str, float | None], None]  # (Detailtext, Prozent 0..100 oder None = unbekannt)


def mb(value: float | None) -> str:
    return f"{(value or 0) / 1_048_576:.1f}"


def progress_text(d: dict) -> tuple[str, float | None] | None:
    """yt-dlp-Fortschritt → („x von y MB · z MB/s“, Prozent); None, wenn gerade nicht geladen wird."""
    if d.get("status") != "downloading":
        return None
    total = d.get("total_bytes") or d.get("total_bytes_estimate")
    done = d.get("downloaded_bytes", 0)
    detail = t("progress.mb_of", done=mb(done), total=mb(total)) if total else t("progress.mb", mb=mb(done))
    if d.get("speed"):
        detail += f" · {t('progress.speed', speed=mb(d['speed']))}"
    return detail, min(100.0, done / total * 100) if total else None


def download_hook(on_progress: ProgressText) -> Callable[[dict], None]:
    def hook(d: dict) -> None:
        if (text := progress_text(d)) is not None:
            on_progress(*text)
    return hook


def base_opts() -> dict:
    """Optionen für jeden Aufruf – bei jedem Versuch neu bauen, damit eine Wiederholung die Cookies erhält."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        # Bei einer Video-URL mit &list=... (z.B. aus einem Mix) nur das Video nehmen.
        # Reine Playlist-URLs (…/playlist?list=…) werden trotzdem komplett geladen.
        "noplaylist": True,
        # Fehler werfen (nicht verschlucken), damit z.B. die Bot-Prüfung erkannt wird
        "ignoreerrors": False,
    }
    # yt-dlp braucht für YouTube eine JavaScript-Umgebung; standardmäßig sucht es nur deno
    if shutil.which("deno") is None and (node := shutil.which("node")):
        opts["js_runtimes"] = {"node": {"path": node}}
    if ffmpeg.location():
        opts["ffmpeg_location"] = ffmpeg.location()
    opts.update(youtube.cookie_opts())
    return opts


def extract_info(url: str, **extra) -> dict | None:
    """Infos abfragen, ohne etwas herunterzuladen."""
    def call() -> dict | None:
        with YoutubeDL({**base_opts(), **extra}) as ydl:
            return ydl.extract_info(url, download=False)

    return youtube.with_cookie_fallback(call)


def download(url: str, outtmpl: Path, fmt: str, on_progress: ProgressText | None = None, **extra) -> None:
    """Lädt `url` nach `outtmpl` (z.B. ordner/audio.%(ext)s); `extra` ergänzt bzw. überschreibt Optionen."""
    opts = {
        "format": fmt,
        "outtmpl": str(outtmpl),
        "concurrent_fragment_downloads": 4,
        "progress_hooks": [download_hook(on_progress)] if on_progress else [],
        **extra,
    }

    def call() -> None:
        with YoutubeDL({**base_opts(), **opts}) as ydl:
            ydl.download([url])

    youtube.with_cookie_fallback(call)
