"""Länger laufende Vorgänge (Prüfen, Album-Analyse, Scan) im Hintergrund – mit Schrittprotokoll für die Oberfläche."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from .errors import clean_error

RUNNING = "läuft"
DONE = "fertig"
NOTHING = "nichts gefunden"
SKIPPED = "übersprungen"
FAILED = "fehler"

MAX_KEPT = 30


@dataclass
class Step:
    label: str
    state: str = RUNNING
    detail: str = ""
    progress: float | None = None  # 0..100, None = unbestimmt
    started: float = field(default_factory=lambda: time.time())  # zur Laufzeit nachschlagen (testbar)
    ended: float | None = None

    def update(self, detail: str | None = None, progress: float | None = None) -> None:
        if detail is not None:
            self.detail = detail
        if progress is not None:
            self.progress = max(0.0, min(100.0, progress))

    def done(self, detail: str = "") -> None:
        self.state, self.detail, self.progress, self.ended = DONE, detail or self.detail, None, time.time()

    def nothing(self, detail: str = "") -> None:
        self.state, self.detail, self.progress, self.ended = NOTHING, detail or self.detail, None, time.time()

    def to_dict(self) -> dict:
        # Laufzeit in ganzen Sekunden – ändert sich jede Sekunde, damit die Oberfläche „· 4 s“ hochzählen kann
        elapsed = (self.ended or time.time()) - self.started
        return {"label": self.label, "state": self.state, "detail": self.detail,
                "progress": None if self.progress is None else round(self.progress, 1),
                "elapsed": int(elapsed)}


@dataclass
class Activity:
    id: str
    kind: str
    status: str = RUNNING
    steps: list[Step] = field(default_factory=list)
    result: dict | None = None
    error: str = ""
    created: float = field(default_factory=time.time)

    def step(self, label: str, detail: str = "") -> Step:
        """Beginnt einen neuen Schritt; ein noch laufender vorheriger Schritt gilt als fertig."""
        for previous in self.steps:
            if previous.state == RUNNING:
                previous.done()
        step = Step(label, detail=detail)
        self.steps.append(step)
        return step

    def skip(self, label: str, detail: str = "") -> None:
        now = time.time()
        self.steps.append(Step(label, state=SKIPPED, detail=detail, started=now, ended=now))

    def log(self) -> list[dict]:
        return [s.to_dict() for s in list(self.steps)]

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "status": self.status, "steps": self.log(),
                "result": self.result if self.status == DONE else None, "error": self.error}


class NullActivity(Activity):
    """Für Aufrufe ohne Oberfläche (CLI, Tests)."""

    def __init__(self) -> None:
        super().__init__(id="", kind="")


class ActivityManager:
    def __init__(self, format_error: Callable[[str], str] | None = None) -> None:
        self._items: dict[str, Activity] = {}
        self._lock = threading.Lock()
        self._format_error = format_error or (lambda message: message)

    def start(self, kind: str, func: Callable[[Activity], dict]) -> Activity:
        activity = Activity(id=uuid.uuid4().hex[:10], kind=kind)
        with self._lock:
            self._items[activity.id] = activity
            for old in sorted(self._items.values(), key=lambda a: a.created)[:-MAX_KEPT]:
                del self._items[old.id]
        threading.Thread(target=self._run, args=(activity, func, self._format_error), daemon=True).start()
        return activity

    def get(self, activity_id: str) -> Activity | None:
        with self._lock:
            return self._items.get(activity_id)

    @staticmethod
    def _run(activity: Activity, func: Callable[[Activity], dict], format_error=lambda m: m) -> None:
        try:
            result = func(activity)
            for step in activity.steps:
                if step.state == RUNNING:
                    step.done()
            activity.result, activity.status = result, DONE
        except Exception as exc:
            message = format_error(clean_error(exc))
            running = next((s for s in reversed(activity.steps) if s.state == RUNNING), None)
            if running:
                running.state, running.detail, running.progress, running.ended = FAILED, message, None, time.time()
                activity.error = f"Fehler bei „{running.label}“: {message}"
            else:
                activity.error = message
            activity.status = FAILED
