"""yt-dlp-Anbindung: Metadaten abfragen, herunterladen, zu MP3 konvertieren, taggen, ablegen."""

from __future__ import annotations

import argparse
import shutil
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from yt_dlp import YoutubeDL

from .activity import Activity, NullActivity

from .config import AUDIO_FORMATS, Config, load_config, to_local_path
from .metadata import MUSIK, PODCAST, Item, apply_playlist, music_item, podcast_item
from .covers import CoverError, fetch_cover
from .paths import target_path, win_path
from .split import encode
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


# ---------- YouTube-Anmeldung (Cookies) gegen die Bot-Prüfung ----------

BROWSERS = ("firefox", "chrome", "chromium", "edge", "brave", "opera", "vivaldi", "safari", "whale")
_BOT_CHECK = ("not a bot", "confirm you’re not", "confirm you're not", "confirm that you're not")
_auth: dict = {"browser": "", "file": None, "sleep": 0, "tmp": None, "active_until": 0.0, "last_bot_check": 0.0}
COOKIE_COPY_MAX_AGE = 15 * 60  # Sekunden
COOKIE_WINDOW = 60 * 60  # nach einer Bot-Prüfung so lange mit Anmeldung laden, danach wieder ohne


def configure_auth(cfg: Config) -> None:
    """Cookie- und Pausen-Einstellungen übernehmen (beim Start und nach Änderung in den Einstellungen)."""
    _auth.update(browser=cfg.cookies_from_browser, file=cfg.cookies_file, sleep=cfg.sleep_seconds,
                 tmp=cfg.data_dir / "tmp")


def cookies_configured() -> bool:
    return bool(_auth["file"] or _auth["browser"])


def cookies_active() -> bool:
    return time.time() < _auth["active_until"]


def note_bot_check() -> None:
    """YouTube hat eine Bot-Prüfung verlangt – für den Hinweis in der Oberfläche merken."""
    _auth["last_bot_check"] = time.time()


def auth_status() -> dict:
    """Für die Oberfläche: wurde YouTube zuletzt misstrauisch, und läuft gerade alles mit Anmeldung?"""
    now = time.time()
    return {
        "cookies_configured": cookies_configured(),
        "cookies_active": cookies_active(),
        "cookies_until": _auth["active_until"] if cookies_active() else None,
        "last_bot_check": _auth["last_bot_check"] or None,
        "recent_bot_check": now - _auth["last_bot_check"] < COOKIE_WINDOW if _auth["last_bot_check"] else False,
    }


def with_cookie_fallback(call):
    """Führt einen yt-dlp-Aufruf zuerst ohne Anmeldung aus. Verlangt YouTube eine Bot-Prüfung und sind Cookies
    hinterlegt, wird derselbe Aufruf sofort mit Cookies wiederholt; danach laden alle Aufrufe COOKIE_WINDOW lang
    mit Anmeldung (die Sperre hält erfahrungsgemäß eine Weile an). Ohne Cookies wird der Fehler weitergereicht.

    `call` muss seine Optionen bei jedem Aufruf neu über _base_opts() bauen, damit die Wiederholung die Cookies erhält."""
    used_cookies = cookies_active()
    try:
        return call()
    except Exception as exc:
        if not is_bot_check(str(exc)):
            raise
        note_bot_check()
        if used_cookies or not cookies_configured():
            raise
        _auth["active_until"] = max(_auth["active_until"], time.time() + COOKIE_WINDOW)
        return call()


def is_bot_check(message: str) -> bool:
    """YouTube-Meldung „Sign in to confirm you’re not a bot“ (nicht zu verwechseln mit der Altersprüfung)."""
    lower = message.lower()
    return any(p in lower for p in _BOT_CHECK)


BOT_CHECK_HINT = ("YouTube verlangt eine Bestätigung, dass du kein Bot bist (zu viele Anfragen von deiner "
                  "Internetverbindung). Abhilfe: unter ⚙ Einstellungen → „YouTube-Anmeldung“ Cookies hinterlegen "
                  "oder es später erneut versuchen – die Sperre hebt sich meist nach einigen Stunden.")


def friendly_error(message: str) -> str:
    return BOT_CHECK_HINT if is_bot_check(message) else message


def parse_browser_spec(spec: str) -> tuple:
    """„firefox“ bzw. „firefox:/pfad/zum/profil“ (Windows-Pfade erlaubt) → Tupel für yt-dlp."""
    browser, _, profile = spec.strip().partition(":")
    browser = browser.strip().lower()
    if browser not in BROWSERS:
        raise ValueError(f"Unbekannter Browser: {browser!r} (möglich: {', '.join(BROWSERS)})")
    if profile.strip():
        return (browser, str(to_local_path(profile.strip())), None, None)
    return (browser, None, None, None)


def _cookie_opts() -> dict:
    # Cookies nur, solange nach einer Bot-Prüfung das Anmelde-Fenster läuft – sonst wird ohne Konto geladen
    if not cookies_active():
        return {}
    if _auth["file"]:
        # yt-dlp schreibt die Cookie-Datei am Ende zurück – bei parallelen Downloads würden sich die Schreibvorgänge
        # in die Quere kommen. Deshalb bekommt jeder Lauf eine eigene, kurzlebige Kopie; das Original bleibt unverändert.
        tmp: Path = _auth["tmp"]
        tmp.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for old in tmp.glob("cookies-*.txt"):
            if now - old.stat().st_mtime > COOKIE_COPY_MAX_AGE:
                old.unlink(missing_ok=True)
        copy = tmp / f"cookies-{uuid.uuid4().hex}.txt"
        shutil.copyfile(_auth["file"], copy)
        return {"cookiefile": str(copy)}
    if _auth["browser"]:
        return {"cookiesfrombrowser": parse_browser_spec(_auth["browser"])}
    return {}


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
    opts.update(_cookie_opts())
    return opts


def is_album_video(info: dict) -> bool:
    """Einzelvideo, das vermutlich ein ganzes Album enthält (Kapitel oder sehr lang)."""
    return info.get("_type") != "playlist" and (
        len(info.get("chapters") or []) >= 3 or (info.get("duration") or 0) >= ALBUM_VIDEO_MIN_DURATION
    )


def _extract(url: str, **extra) -> dict | None:
    """Infos abfragen; Fehler werden geworfen (nicht verschluckt), damit z.B. die Bot-Prüfung erkannt wird."""
    with YoutubeDL({**_base_opts(), "ignoreerrors": False, **extra}) as ydl:
        return ydl.extract_info(url, download=False)


def _entry_url(entry: dict) -> str:
    url = entry.get("url") or entry.get("webpage_url") or ""
    if url.startswith("http"):
        return url
    return f"https://www.youtube.com/watch?v={entry.get('id')}"


def probe(url: str, mode: str, cfg: Config, activity: Activity | None = None) -> dict:
    """Lädt nur die Metadaten (Einzelvideo oder alle Playlist-Einträge) – Schritte landen im Protokoll."""
    act = activity or NullActivity()
    step = act.step("Video-Infos laden")
    info = with_cookie_fallback(lambda: _extract(url, extract_flat="in_playlist"))
    if not info:
        raise ValueError("Keine Informationen gefunden – ist die URL korrekt und das Video verfügbar?")

    is_playlist = info.get("_type") == "playlist"
    if is_playlist:
        flat = [e for e in (info.get("entries") or []) if e]
        step.done(f"Playlist „{info.get('title') or ''}“ mit {len(flat)} Einträgen")
        details = act.step("Details der Titel laden", f"0/{len(flat)}")
        entries: list[dict | None] = [None] * len(flat)
        finished = 0

        bot_errors: list[str] = []

        def load(index: int) -> None:
            try:
                entries[index] = with_cookie_fallback(lambda: _extract(_entry_url(flat[index])))
            except Exception as exc:  # einzelner Titel nicht verfügbar → überspringen; Bot-Prüfung → abbrechen
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
KEEP_BOTH, OVERWRITE, SKIP = "keep_both", "overwrite", "skip"
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class Skipped(Exception):
    """Zieldatei existiert und der Titel soll übersprungen werden."""


def audio_format(item: Item, cfg: Config) -> str:
    return item.audio_format if item.audio_format in AUDIO_FORMATS else cfg.audio_format


def final_path(item: Item, cfg: Config) -> Path:
    """Zielpfad inkl. Endung des gewählten Formats (ohne Kollisionsbehandlung)."""
    root = Path(item.target_root) if item.target_root else cfg.root(item.mode)
    return target_path(item, root).with_suffix(f".{audio_format(item, cfg)}")


def place(src: Path, item: Item, cfg: Config) -> Path:
    """Verschiebt die fertige Datei an ihren Zielort – je nach item.on_conflict:
    keep_both → „… (2)“, overwrite → ersetzen, skip → Skipped. Gesperrt, damit parallele Titel
    mit gleichem Namen nicht beide denselben freien Dateinamen wählen."""
    target = final_path(item, cfg)
    with _PLACE_LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if item.on_conflict == SKIP:
                raise Skipped(f"übersprungen – existiert bereits: {target.name}")
            if item.on_conflict == OVERWRITE:
                # erst neben das Ziel kopieren, dann atomar ersetzen – bei Fehlern bleibt die alte Datei
                staging = target.with_name(f".{target.stem}.neu{target.suffix}")
                shutil.move(str(src), staging)
                staging.replace(target)
                item.overwritten = True
                return target
            target = _unique(target)
        shutil.move(str(src), target)
    return target


def conflicts(items: list[Item], cfg: Config) -> list[dict]:
    """Titel, deren Zieldatei schon existiert – für den Dialog in der Oberfläche."""
    found = []
    for item in items:
        path = final_path(item, cfg)
        if path.exists():
            stat = path.stat()
            found.append({"id": item.id, "label": item.label, "path": str(path), "win_path": win_path(path), "size": stat.st_size, "modified": stat.st_mtime})
    return found


def _mb(value: float | None) -> str:
    return f"{(value or 0) / 1_048_576:.1f}"


def choose_cover(item: Item, cfg: Config, thumbnail: Path | None, report) -> tuple[Path | None, bool]:
    """Eigenes Cover (falls angegeben und ladbar), sonst das YouTube-Vorschaubild (quadratisch zugeschnitten)."""
    if item.cover_url:
        try:
            return fetch_cover(item.cover_url, cfg.data_dir / "covers"), item.cover_crop
        except CoverError as exc:
            report("taggt", 85.0, f"{exc} – nehme das YouTube-Vorschaubild")
    return thumbnail, True


def work_dir(cfg: Config, item: Item) -> Path:
    return cfg.data_dir / "work" / f"{item.mode}-{item.id}"


def fetch(item: Item, cfg: Config, progress: ProgressCallback | None = None) -> Path:
    """Stufe 1 (Netzwerk): Audiospur + Vorschaubild in ein Arbeitsverzeichnis laden. Gibt das Verzeichnis zurück."""
    report = progress or (lambda status, pct, detail="": None)
    fmt = audio_format(item, cfg)
    folder = work_dir(cfg, item)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)

    def on_download(d: dict) -> None:
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            detail = f"{_mb(done)} von {_mb(total)} MB" if total else f"{_mb(done)} MB"
            if d.get("speed"):
                detail += f" · {_mb(d['speed'])} MB/s"
            report("lädt", min(100.0, done / total * 100) if total else 0.0, detail)

    opts = {
        "ignoreerrors": False,
        # für M4A gleich die AAC-Spur nehmen – dann wird nur umverpackt, nicht neu kodiert
        "format": "bestaudio[ext=m4a]/bestaudio/best" if fmt == "m4a" else "bestaudio/best",
        "outtmpl": str(folder / "source.%(ext)s"),
        "writethumbnail": True,
        "concurrent_fragment_downloads": 4,
        "retry_sleep_functions": {"http": lambda n: min(30, 2 ** n), "fragment": lambda n: min(30, 2 ** n)},
        "progress_hooks": [on_download],
    }
    if _auth["sleep"]:  # Pause vor dem Download (zufällig n…2n s), um YouTube nicht zu viele Anfragen zu schicken
        opts.update(sleep_interval=_auth["sleep"], max_sleep_interval=_auth["sleep"] * 2)
    report("lädt", 0.0)

    def run() -> None:
        with YoutubeDL({**_base_opts(), **opts}) as ydl:  # _base_opts() je Versuch → Cookies bei der Wiederholung
            ydl.download([item.url or item.id])

    try:
        with_cookie_fallback(run)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return folder


def convert(item: Item, cfg: Config, progress: ProgressCallback | None, folder: Path) -> Path:
    """Stufe 2 (CPU): umwandeln (ffmpeg), taggen, ablegen, Arbeitsverzeichnis aufräumen."""
    report = progress or (lambda status, pct, detail="": None)
    fmt = audio_format(item, cfg)
    files = [p for p in folder.glob("source.*") if not p.name.endswith((".part", ".ytdl"))]
    source = next((p for p in files if p.suffix.lower() not in _IMAGE_SUFFIXES), None)
    if source is None:
        raise RuntimeError("Heruntergeladene Datei fehlt – bitte erneut versuchen")
    thumb = next((p for p in files if p.suffix.lower() in _IMAGE_SUFFIXES), None)
    try:
        report("konvertiert", 0.0, f"{source.suffix.lstrip('.').upper()} → {fmt.upper()}")
        out = folder / f"out.{fmt}"
        encode(source, out, cfg.bitrate)
        report("taggt", 80.0)
        cover, crop = choose_cover(item, cfg, thumb, report)
        write_tags(out, item, cover, crop)
        target = place(out, item, cfg)
    except Skipped:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    shutil.rmtree(folder, ignore_errors=True)
    Archive(cfg.data_dir, item.mode).add(item.id)
    report("fertig", 100.0)
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
    result = probe(args.url, args.mode, cfg)
    for data in result["items"]:
        item = Item.from_dict(data)
        print(f"{item.artist} - {item.title}  [{item.album or '-'}]  ← {item.source_title}")
        if not args.probe:
            path = download(item, cfg, lambda s, p: print(f"  {s} {p:5.1f}%", end="\r"))
            print(f"\n  → {path}")


if __name__ == "__main__":
    main()
