"""Einstellungen aus der Oberfläche: je Feld eine Prüfung, die den Wert für .env und für die Config liefert."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .auth import parse_browser_spec
from .config import AUDIO_FORMATS, Config, to_local_path
from .i18n import t

BITRATES = (128, 160, 192, 256, 320)


class InvalidSettings(ValueError):
    def __init__(self, fields: dict[str, str]):
        super().__init__(t("settings.not_saved"))
        self.fields = fields


def _folder(value: str) -> tuple[str, Path | None]:
    """Leer = nicht eingestellt. Sonst muss der Ordner existieren oder sich anlegen lassen und beschreibbar sein."""
    if not value.strip():
        return "", None
    path = to_local_path(value)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(t("settings.folder_create", error=exc.strerror or exc)) from exc
    if not os.access(path, os.W_OK):
        raise ValueError(t("settings.folder_not_writable"))
    return value.strip(), path


def _cookie_file(value: str) -> tuple[str, Path | None]:
    if not value.strip():
        return "", None
    path = to_local_path(value)
    if not path.is_file():
        raise ValueError(t("settings.file_not_found"))
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError as exc:
        raise ValueError(t("settings.file_unreadable", error=exc.strerror or exc)) from exc
    if "Netscape HTTP Cookie File" not in head and "\t" not in head:
        raise ValueError(t("settings.not_netscape"))
    return value.strip(), path


def _browser(value: str) -> tuple[str, str]:
    spec = value.strip()
    parsed = parse_browser_spec(spec) if spec else None  # ValueError bei unbekanntem Browser
    if parsed and parsed[1] and not Path(parsed[1]).exists():
        raise ValueError(t("settings.profile_not_found"))
    return spec, spec


def _one_of(options: tuple, message: Callable[[], str]) -> Callable[[Any], tuple[str, Any]]:
    """Prüfung auf erlaubte Werte; die Meldung wird erst beim Fehler erzeugt (in der dann eingestellten Sprache)."""
    def check(value: Any) -> tuple[str, Any]:
        if value not in options:
            raise ValueError(message())
        return str(value), value
    return check


def _between(low: int, high: int) -> Callable[[int], tuple[str, int]]:
    return _one_of(tuple(range(low, high + 1)), lambda: t("settings.allowed_range", low=low, high=high))


def _env(key: str) -> Callable[[Config], str]:
    """So, wie es eingetragen wurde (z.B. Windows-Pfad), damit man es wiedererkennt."""
    return lambda cfg: os.getenv(key, "").strip()


def _attr(name: str) -> Callable[[Config], Any]:
    return lambda cfg: getattr(cfg, name)


@dataclass(frozen=True)
class Setting:
    env_key: str
    check: Callable[[Any], tuple[str, Any]]  # → (Wert für .env, Wert für Config); ValueError mit Meldung
    current: Callable[[Config], Any]
    limits: tuple[int, int] | None = None  # für min/max der Eingabefelder


def _number(env_key: str, field: str, low: int, high: int) -> Setting:
    return Setting(env_key, _between(low, high), _attr(field), (low, high))


SETTINGS: dict[str, Setting] = {
    "musik_dir": Setting("MUSIK_DIR", _folder, _env("MUSIK_DIR")),
    "podcast_dir": Setting("PODCAST_DIR", _folder, _env("PODCAST_DIR")),
    "audio_format": Setting("AUDIO_FORMAT", _one_of(AUDIO_FORMATS, lambda: t("settings.or").join(AUDIO_FORMATS)),
                            _attr("audio_format")),
    "bitrate": Setting("BITRATE", _one_of(BITRATES, lambda: t("settings.allowed_values", values=", ".join(map(str, BITRATES)))),
                       _attr("bitrate")),
    "parallel_downloads": _number("PARALLEL_DOWNLOADS", "parallel_downloads", 1, 16),
    "parallel_cuts": _number("PARALLEL_CUTS", "parallel_cuts", 1, 32),
    "max_retries": _number("MAX_RETRIES", "max_retries", 0, 10),
    "cookies_from_browser": Setting("COOKIES_FROM_BROWSER", _browser, _attr("cookies_from_browser")),
    "cookies_file": Setting("COOKIES_FILE", _cookie_file, _env("COOKIES_FILE")),
    "sleep_seconds": _number("SLEEP_SECONDS", "sleep_seconds", 0, 120),
}


def current(cfg: Config) -> dict:
    """Werte für den Einstellungsdialog."""
    return {field: setting.current(cfg) for field, setting in SETTINGS.items()}


def limits() -> dict[str, list[int]]:
    return {field: list(s.limits) for field, s in SETTINGS.items() if s.limits}


def validate(values: dict) -> tuple[dict[str, str], dict[str, Any]]:
    """Prüft die gesendeten Felder. Liefert (Werte für .env, Werte für die Config) – oder wirft InvalidSettings mit
    einer Meldung je Feld; dann wird nichts übernommen."""
    env: dict[str, str] = {}
    changes: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for field, value in values.items():
        setting = SETTINGS[field]
        try:
            env[setting.env_key], changes[field] = setting.check(value)
        except ValueError as exc:
            errors[field] = str(exc)
    if errors:
        raise InvalidSettings(errors)
    return env, changes
