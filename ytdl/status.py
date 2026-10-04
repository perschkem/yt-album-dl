"""Status-Texte für Titel, Hintergrund-Vorgänge und die Historie – an einer Stelle.

Die Werte erscheinen so in der Oberfläche, in den CSS-Klassen und in data/history.jsonl; deshalb dürfen sie sich
nicht ändern. Als StrEnum sind sie gewöhnliche Strings (Vergleich mit "fertig", JSON, f-Strings)."""

from __future__ import annotations

from enum import StrEnum


class Status(StrEnum):
    # gemeinsam (Titel, Vorgang, Historie)
    DONE = "fertig"
    FAILED = "fehler"
    SKIPPED = "übersprungen"
    # Titel in der Warteschlange
    WAITING = "wartet"
    WAITING_FOR_CONVERT = "wartet auf Konvertierung"
    DOWNLOADING = "lädt"
    CONVERTING = "konvertiert"
    CUTTING = "schneidet"
    TAGGING = "taggt"
    RETRYING = "neuer Versuch"
    PAUSED = "pausiert"
    # Schritte eines Hintergrund-Vorgangs
    RUNNING = "läuft"
    NOTHING = "nichts gefunden"
    # Historie: vorhandene Datei ersetzt
    OVERWRITTEN = "überschrieben"


# Titel ist abgeschlossen – egal mit welchem Ergebnis
FINISHED = frozenset({Status.DONE, Status.FAILED, Status.SKIPPED})
