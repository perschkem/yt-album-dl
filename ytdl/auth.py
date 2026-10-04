"""YouTube-Anmeldung (Cookies) gegen die Bot-Prüfung „Sign in to confirm you’re not a bot“."""

from __future__ import annotations

import shutil
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from .config import Config, to_local_path

T = TypeVar("T")

BROWSERS = ("firefox", "chrome", "chromium", "edge", "brave", "opera", "vivaldi", "safari", "whale")
_BOT_CHECK = ("not a bot", "confirm you’re not", "confirm you're not", "confirm that you're not")
COOKIE_COPY_MAX_AGE = 15 * 60  # Sekunden
COOKIE_WINDOW = 60 * 60  # nach einer Bot-Prüfung so lange mit Anmeldung laden, danach wieder ohne

BOT_CHECK_HINT = ("YouTube verlangt eine Bestätigung, dass du kein Bot bist (zu viele Anfragen von deiner "
                  "Internetverbindung). Abhilfe: unter ⚙ Einstellungen → „YouTube-Anmeldung“ Cookies hinterlegen "
                  "oder es später erneut versuchen – die Sperre hebt sich meist nach einigen Stunden.")


def is_bot_check(message: str) -> bool:
    """YouTube-Meldung „Sign in to confirm you’re not a bot“ (nicht zu verwechseln mit der Altersprüfung)."""
    lower = message.lower()
    return any(p in lower for p in _BOT_CHECK)


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


class YoutubeAuth:
    """Cookie-Einstellungen und der Zustand nach einer Bot-Prüfung (seit wann, bis wann mit Anmeldung)."""

    def __init__(self) -> None:
        self.browser = ""
        self.file: Path | None = None
        self.sleep = 0  # Pause vor jedem Download (zufällig n…2n s)
        self.tmp: Path | None = None  # für die kurzlebigen Kopien der Cookie-Datei
        self.active_until = 0.0
        self.last_bot_check = 0.0

    def configure(self, cfg: Config) -> None:
        """Cookie- und Pausen-Einstellungen übernehmen (beim Start und nach Änderung in den Einstellungen)."""
        self.browser, self.file, self.sleep = cfg.cookies_from_browser, cfg.cookies_file, cfg.sleep_seconds
        self.tmp = cfg.data_dir / "tmp"

    def cookies_configured(self) -> bool:
        return bool(self.file or self.browser)

    def cookies_active(self) -> bool:
        return time.time() < self.active_until

    def note_bot_check(self) -> None:
        """YouTube hat eine Bot-Prüfung verlangt – für den Hinweis in der Oberfläche merken."""
        self.last_bot_check = time.time()

    def status(self) -> dict:
        """Für die Oberfläche: wurde YouTube zuletzt misstrauisch, und läuft gerade alles mit Anmeldung?"""
        active = self.cookies_active()
        return {
            "cookies_configured": self.cookies_configured(),
            "cookies_active": active,
            "cookies_until": self.active_until if active else None,
            "last_bot_check": self.last_bot_check or None,
            "recent_bot_check": bool(self.last_bot_check) and time.time() - self.last_bot_check < COOKIE_WINDOW,
        }

    def with_cookie_fallback(self, call: Callable[[], T]) -> T:
        """Führt einen yt-dlp-Aufruf zuerst ohne Anmeldung aus. Verlangt YouTube eine Bot-Prüfung und sind Cookies
        hinterlegt, wird derselbe Aufruf sofort mit Cookies wiederholt; danach laden alle Aufrufe COOKIE_WINDOW lang
        mit Anmeldung (die Sperre hält erfahrungsgemäß eine Weile an). Ohne Cookies wird der Fehler weitergereicht.

        `call` muss seine Optionen bei jedem Aufruf neu über cookie_opts() bauen (ytdlp.base_opts tut das), damit
        die Wiederholung die Cookies erhält."""
        used_cookies = self.cookies_active()
        try:
            return call()
        except Exception as exc:
            if not is_bot_check(str(exc)):
                raise
            self.note_bot_check()
            if used_cookies or not self.cookies_configured():
                raise
            self.active_until = max(self.active_until, time.time() + COOKIE_WINDOW)
            return call()

    def cookie_opts(self) -> dict:
        """yt-dlp-Optionen für die Anmeldung – nur, solange nach einer Bot-Prüfung das Anmelde-Fenster läuft."""
        if not self.cookies_active():
            return {}
        if self.file:
            return {"cookiefile": str(self._cookie_copy())}
        if self.browser:
            return {"cookiesfrombrowser": parse_browser_spec(self.browser)}
        return {}

    def _cookie_copy(self) -> Path:
        # yt-dlp schreibt die Cookie-Datei am Ende zurück – bei parallelen Downloads würden sich die Schreibvorgänge
        # in die Quere kommen. Deshalb bekommt jeder Lauf eine eigene, kurzlebige Kopie; das Original bleibt unverändert.
        assert self.tmp is not None and self.file is not None
        self.tmp.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for old in self.tmp.glob("cookies-*.txt"):
            if now - old.stat().st_mtime > COOKIE_COPY_MAX_AGE:
                old.unlink(missing_ok=True)
        copy = self.tmp / f"cookies-{uuid.uuid4().hex}.txt"
        shutil.copyfile(self.file, copy)
        return copy


youtube = YoutubeAuth()  # gemeinsamer Zustand für alle yt-dlp-Aufrufe
