"""Fehlermeldungen für die Oberfläche aufbereiten."""

from __future__ import annotations


def clean_error(exc: BaseException | str) -> str:
    """Meldung ohne das „ERROR: “-Präfix von yt-dlp und ohne Leerraum am Rand."""
    return str(exc).removeprefix("ERROR: ").strip()


class PermanentError(RuntimeError):
    """Fehler, bei dem ein neuer Versuch nichts bringt (z.B. zwischengespeichertes Audio fehlt) – unabhängig von
    der Sprache der Meldung."""


class InvalidVideoId(PermanentError, ValueError):
    pass
