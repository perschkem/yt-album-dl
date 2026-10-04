"""Warteschlange: Titel werden nacheinander in einem Hintergrund-Thread heruntergeladen."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field

from .config import Config
from .downloader import download
from .metadata import Item

MAX_JOBS_KEPT = 50


@dataclass
class Task:
    item: Item
    status: str = "wartet"  # wartet | lädt | konvertiert | taggt | fertig | fehler
    progress: float = 0.0
    path: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.item.id,
            "label": f"{self.item.artist} - {self.item.title}",
            "status": self.status,
            "progress": round(self.progress, 1),
            "path": self.path,
            "error": self.error,
        }


@dataclass
class Job:
    id: str
    title: str
    mode: str
    tasks: list[Task]
    created: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        done = sum(t.status in ("fertig", "fehler") for t in self.tasks)
        return {
            "id": self.id,
            "title": self.title,
            "mode": self.mode,
            "created": self.created,
            "done": done,
            "total": len(self.tasks),
            "tasks": [t.to_dict() for t in self.tasks],
        }


class JobManager:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.jobs: list[Job] = []
        self._queue: queue.Queue[Task] = queue.Queue()
        self._lock = threading.Lock()
        threading.Thread(target=self._worker, daemon=True, name="ytdl-worker").start()

    def submit(self, title: str, mode: str, items: list[Item]) -> Job:
        job = Job(id=uuid.uuid4().hex[:8], title=title, mode=mode, tasks=[Task(item=i) for i in items])
        with self._lock:
            self.jobs.insert(0, job)
            del self.jobs[MAX_JOBS_KEPT:]
        for task in job.tasks:
            self._queue.put(task)
        return job

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [job.to_dict() for job in self.jobs]

    def _worker(self) -> None:
        while True:
            task = self._queue.get()

            def report(status: str, pct: float, task: Task = task) -> None:
                task.status, task.progress = status, pct

            try:
                task.path = str(download(task.item, self.cfg, report))
            except Exception as exc:  # Fehler eines Titels soll die Warteschlange nicht stoppen
                task.status, task.error = "fehler", str(exc).removeprefix("ERROR: ")
            finally:
                self._queue.task_done()
