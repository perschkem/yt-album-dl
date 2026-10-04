"""Warteschlange: mehrere Worker laden/schneiden parallel, mit exponentiellem Backoff pro Titel."""

from __future__ import annotations

import os
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .albumvideo import cut_track
from .config import Config
from .downloader import download
from .metadata import Item
from .paths import to_windows_path

MAX_JOBS_KEPT = 50
BACKOFF_BASE = 2.0  # Sekunden vor dem 1. neuen Versuch
BACKOFF_MAX = 120.0
BACKOFF_JITTER = 0.2  # ±20 %, damit parallele Worker nicht gleichzeitig erneut anfragen
THROTTLE_SECONDS = 120.0  # nach HTTP 429 so lange nur ein Download gleichzeitig

DOWNLOAD = "download"
CUT = "cut"

# Fehler, bei denen ein neuer Versuch nichts bringt
_PERMANENT = (
    "private video", "video unavailable", "has been removed", "been terminated", "sign in to confirm your age",
    "age-restricted", "members-only", "join this channel", "not available in your country", "copyright",
    "is not a valid url", "unsupported url", "zwischengespeichertes audio fehlt", "ungültige",
)
_THROTTLED = ("429", "too many requests", "rate limit", "rate-limit")


def backoff_delay(attempt: int, rng=random.random) -> float:
    """Wartezeit vor dem nächsten Versuch: 2 s, 4 s, 8 s, 16 s … max. 2 Min., mit ±20 % Zufall."""
    delay = min(BACKOFF_MAX, BACKOFF_BASE * 2 ** (attempt - 1))
    return delay * (1 + BACKOFF_JITTER * (2 * rng() - 1))


def is_permanent(message: str) -> bool:
    lower = message.lower()
    return any(p in lower for p in _PERMANENT)


def is_throttled(message: str) -> bool:
    lower = message.lower()
    return any(p in lower for p in _THROTTLED)


@dataclass
class Task:
    item: Item
    kind: str
    status: str = "wartet"  # wartet | lädt | konvertiert | schneidet | taggt | neuer Versuch | fertig | fehler
    progress: float = 0.0
    detail: str = ""
    path: str = ""
    error: str = ""
    attempt: int = 1
    next_try: float = 0.0

    def to_dict(self, max_attempts: int) -> dict:
        wait = max(0.0, self.next_try - time.time()) if self.status == "neuer Versuch" else 0.0
        return {
            "id": self.item.id,
            "label": f"{self.item.artist} - {self.item.title}",
            "status": self.status,
            "progress": round(self.progress, 1),
            "detail": self.detail,
            "path": self.path,
            "win_path": to_windows_path(Path(self.path)) if self.path else "",
            "error": self.error,
            "attempt": self.attempt,
            "max_attempts": max_attempts,
            "retry_in": round(wait),
        }


@dataclass
class Job:
    id: str
    title: str
    mode: str
    tasks: list[Task]
    created: float = field(default_factory=time.time)

    def folder(self) -> str:
        """Gemeinsamer Ordner der fertigen Titel (Album-/Kanalordner)."""
        paths = [t.path for t in self.tasks if t.path]
        if not paths:
            return ""
        return os.path.commonpath([str(Path(p).parent) for p in paths])

    def to_dict(self, max_attempts: int) -> dict:
        folder = self.folder()
        return {
            "id": self.id,
            "title": self.title,
            "mode": self.mode,
            "created": self.created,
            "done": sum(t.status in ("fertig", "fehler") for t in self.tasks),
            "failed": sum(t.status == "fehler" for t in self.tasks),
            "total": len(self.tasks),
            "folder": folder,
            "win_folder": to_windows_path(Path(folder)) if folder else "",
            "tasks": [t.to_dict(max_attempts) for t in self.tasks],
        }


class JobManager:
    def __init__(self, cfg: Config, runners: dict | None = None):
        self.cfg = cfg
        self.jobs: list[Job] = []
        self._runners = runners or {DOWNLOAD: download, CUT: cut_track}
        self._pending: list[Task] = []
        self._active = {DOWNLOAD: 0, CUT: 0}
        self._throttle_until = 0.0
        self._cond = threading.Condition()
        for n in range(cfg.parallel_downloads + cfg.parallel_cuts):
            threading.Thread(target=self._worker, daemon=True, name=f"ytdl-worker-{n}").start()

    @property
    def max_attempts(self) -> int:
        return self.cfg.max_retries + 1

    def submit(self, title: str, mode: str, items: list[Item]) -> Job:
        tasks = [Task(item=i, kind=CUT if i.start is not None else DOWNLOAD) for i in items]
        job = Job(id=uuid.uuid4().hex[:8], title=title, mode=mode, tasks=tasks)
        with self._cond:
            self.jobs.insert(0, job)
            del self.jobs[MAX_JOBS_KEPT:]
            self._pending.extend(tasks)
            self._cond.notify_all()
        return job

    def retry(self, job_id: str, task_id: str | None = None) -> dict:
        """Fehlgeschlagene Titel (alle oder einen) neu einreihen – mit frischem Versuchszähler."""
        with self._cond:
            job = next((j for j in self.jobs if j.id == job_id), None)
            if job is None:
                raise KeyError(job_id)
            for task in job.tasks:
                if task.status == "fehler" and (task_id is None or task.item.id == task_id):
                    task.status, task.progress, task.error, task.detail = "wartet", 0.0, "", ""
                    task.attempt, task.next_try = 1, 0.0
                    self._pending.append(task)
            self._cond.notify_all()
            return job.to_dict(self.max_attempts)

    def snapshot(self) -> list[dict]:
        with self._cond:
            return [job.to_dict(self.max_attempts) for job in self.jobs]

    def _limit(self, kind: str, now: float) -> int:
        if kind == CUT:
            return self.cfg.parallel_cuts
        return 1 if now < self._throttle_until else self.cfg.parallel_downloads

    def _take(self) -> Task:
        """Nächste startbereite Aufgabe (Reihenfolge wie eingereiht); wartet, bis eine verfügbar ist."""
        with self._cond:
            while True:
                now = time.time()
                for task in self._pending:
                    if task.next_try <= now and self._active[task.kind] < self._limit(task.kind, now):
                        self._pending.remove(task)
                        self._active[task.kind] += 1
                        return task
                upcoming = [t.next_try for t in self._pending if t.next_try > now]
                self._cond.wait(timeout=min(upcoming) - now if upcoming else None)

    def _worker(self) -> None:
        while True:
            task = self._take()

            def report(status: str, pct: float, detail: str = "", task: Task = task) -> None:
                task.status, task.progress, task.detail = status, pct, detail

            try:
                task.path = str(self._runners[task.kind](task.item, self.cfg, report))
                task.detail = ""
            except Exception as exc:  # ein Fehler soll die Warteschlange nie stoppen
                self._failed(task, str(exc).removeprefix("ERROR: ").strip())
            finally:
                with self._cond:
                    self._active[task.kind] -= 1
                    self._cond.notify_all()

    def _failed(self, task: Task, message: str) -> None:
        with self._cond:
            if is_throttled(message):
                self._throttle_until = time.time() + THROTTLE_SECONDS
            if is_permanent(message) or task.attempt >= self.max_attempts:
                task.status, task.error, task.detail = "fehler", message, ""
                if task.attempt > 1 and not is_permanent(message):
                    task.error = f"{message} (nach {task.attempt} Versuchen)"
                return
            delay = backoff_delay(task.attempt)
            task.attempt += 1
            task.next_try = time.time() + delay
            task.status, task.progress = "neuer Versuch", 0.0
            task.detail = f"Versuch {task.attempt}/{self.max_attempts} – letzter Fehler: {message[:160]}"
            self._pending.append(task)
            self._cond.notify_all()
