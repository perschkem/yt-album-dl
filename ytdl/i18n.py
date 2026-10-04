"""Übersetzungen: ein Wörterbuch je Sprache (ytdl/locales/<sprache>.json), gemeinsam für Backend und Oberfläche.

Werte sind Texte mit Platzhaltern wie {count}; für Mehrzahl ein Objekt {"one": …, "other": …}, gewählt über den
Parameter count. Die Sprache gilt global (lokale App, ein Nutzer) – Texte entstehen auch in Hintergrund-Threads,
wo es keine Anfrage gibt, aus der man sie ablesen könnte."""

from __future__ import annotations

import json
import re
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "locales"
LANGUAGES = {"de": "Deutsch", "en": "English"}  # Code → Name in der eigenen Sprache
DEFAULT_LANGUAGE = "de"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")

_catalogs: dict[str, dict] = {
    lang: json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8")) for lang in LANGUAGES
}
_language = DEFAULT_LANGUAGE


def configure(language: str) -> None:
    global _language
    if language not in LANGUAGES:
        raise ValueError(f"Unbekannte Sprache: {language!r} (möglich: {', '.join(LANGUAGES)})")
    _language = language


def language() -> str:
    return _language


def messages(lang: str | None = None) -> dict:
    return _catalogs[lang or _language]


def t(key: str, lang: str | None = None, **params) -> str:
    """Text zu `key` in der eingestellten Sprache (fehlt er, auf Deutsch; unbekannt → der Schlüssel selbst)."""
    value = _catalogs[lang or _language].get(key, _catalogs[DEFAULT_LANGUAGE].get(key))
    if value is None:
        return key
    if isinstance(value, dict):
        value = value["one" if params.get("count") == 1 else "other"]
    return _PLACEHOLDER.sub(lambda m: str(params[m.group(1)]) if m.group(1) in params else m.group(0), value)
