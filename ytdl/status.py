"""Status von Titeln, Hintergrund-Vorgängen und Historie-Einträgen – als sprachneutrale Codes.

Die Codes stehen in data/history.jsonl, in CSS-Klassen und in Filtern; angezeigt wird die Übersetzung
(i18n-Schlüssel status.<code>). Als StrEnum sind sie gewöhnliche Strings (Vergleich, JSON, f-Strings)."""

from __future__ import annotations

from enum import StrEnum


class Status(StrEnum):
    # gemeinsam (Titel, Vorgang, Historie)
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    # Titel in der Warteschlange
    WAITING = "waiting"
    WAITING_FOR_CONVERT = "waiting_for_convert"
    DOWNLOADING = "downloading"
    CONVERTING = "converting"
    CUTTING = "cutting"
    TAGGING = "tagging"
    RETRYING = "retrying"
    PAUSED = "paused"
    # Schritte eines Hintergrund-Vorgangs
    RUNNING = "running"
    NOTHING = "nothing"
    # Historie: vorhandene Datei ersetzt
    OVERWRITTEN = "overwritten"


# Titel ist abgeschlossen – egal mit welchem Ergebnis
FINISHED = frozenset({Status.DONE, Status.FAILED, Status.SKIPPED})

# Ältere Historie-Einträge speicherten den deutschen Anzeigetext
LEGACY_RESULTS = {"fertig": Status.DONE, "fehler": Status.FAILED, "übersprungen": Status.SKIPPED,
                  "überschrieben": Status.OVERWRITTEN}
