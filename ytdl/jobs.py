"""Warteschlange als Pipeline: Downloads (Netzwerk) und ffmpeg-Arbeit (CPU) in getrennten Pools,
mit exponentiellem Backoff pro Titel und Stufe."""

from __future__ import annotations

import logging
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .albumvideo import cut_track
from .config import Config
from .downloader import (BOT_CHECK_HINT, Skipped, audio_format, convert, cookies_active, fetch, is_bot_check,
                         note_bot_check)
from .history import History
from .errors import clean_error
from .metadata import Item
from .paths import common_folder, win_path
from .status import FINISHED, Status

log = logging.getLogger(__name__)

MAX_JOBS_KEPT = 50
BACKOFF_BASE = 2.0  # Sekunden vor dem 1. neuen Versuch
BACKOFF_MAX = 120.0
BACKOFF_JITTER = 0.2  # ±20 %, damit parallele Worker nicht gleichzeitig erneut anfragen
THROTTLE_SECONDS = 120.0  # nach HTTP 429 so lange nur ein Download gleichzeitig
BOT_PAUSE_SECONDS = 15 * 60  # nach „Sign in to confirm you’re not a bot“ alle Downloads so lange anhalten
MAX_BOT_PAUSES = 3  # danach gilt der Titel als fehlgeschlagen

# Stufen eines Titels: Download = FETCH → CONVERT, Album-Schnitt = CUT
FETCH = "fetch"
CONVERT = "convert"
CUT = "cut"
# Pools: Netzwerk (PARALLEL_DOWNLOADS) und CPU/ffmpeg (PARALLEL_CUTS)
NET = "net"
CPU = "cpu"
POOL = {FETCH: NET, CONVERT: CPU, CUT: CPU}
# Anteil jeder Stufe am Gesamtbalken eines Titels: Laden 0–70 %, Umwandeln + Taggen 70–100 %
STAGE_RANGE = {FETCH: (0.0, 70.0), CONVERT: (70.0, 100.0), CUT: (0.0, 100.0)}


def overall_progress(stage: str, pct: float) -> float:
    """Fortschritt innerhalb einer Stufe (0–100) → Fortschritt des ganzen Titels (ein durchgehender Balken)."""
    start, end = STAGE_RANGE[stage]
    return start + (end - start) * max(0.0, min(100.0, pct)) / 100

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
    stage: str
    status: str = Status.WAITING
    progress: float = 0.0
    detail: str = ""
    path: str = ""
    error: str = ""
    attempt: int = 1
    next_try: float = 0.0
    workdir: str = ""  # Ergebnis der FETCH-Stufe
    job_id: str = ""
    job_title: str = ""
    bot_pauses: int = 0

    @property
    def pool(self) -> str:
        return POOL[self.stage]

    def to_dict(self, max_attempts: int) -> dict:
        wait = max(0.0, self.next_try - time.time()) if self.status in (Status.RETRYING, Status.PAUSED) else 0.0
        return {
            "id": self.item.id,
            "label": self.item.label,
            "status": self.status,
            "stage": self.stage,
            "progress": round(self.progress, 1),
            "detail": self.detail,
            "path": self.path,
            "win_path": win_path(self.path),
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
    max_attempts: int = 1
    audio_format: str = ""
    created: float = field(default_factory=time.time)

    @property
    def finished(self) -> bool:
        return all(t.status in FINISHED for t in self.tasks)

    def folder(self) -> str:
        """Gemeinsamer Ordner der fertigen Titel (Album-/Kanalordner)."""
        return common_folder([t.path for t in self.tasks if t.path])

    def to_dict(self) -> dict:
        folder = self.folder()
        return {
            "id": self.id,
            "title": self.title,
            "mode": self.mode,
            "audio_format": self.audio_format,
            "created": self.created,
            "done": sum(t.status in FINISHED for t in self.tasks),
            "failed": sum(t.status == Status.FAILED for t in self.tasks),
            "skipped": sum(t.status == Status.SKIPPED for t in self.tasks),
            "total": len(self.tasks),
            "folder": folder,
            "win_folder": win_path(folder),
            "tasks": [t.to_dict(self.max_attempts) for t in self.tasks],
        }


class JobManager:
    def __init__(self, cfg: Config, runners: dict | None = None, history: History | None = None):
        self.cfg = cfg
        self.history = history
        self.jobs: list[Job] = []
        self._runners = runners or {FETCH: fetch, CONVERT: convert, CUT: cut_track}
        self._pending: list[Task] = []
        self._active = {NET: 0, CPU: 0}
        self._throttle_until = 0.0
        self.paused_until = 0.0  # YouTube-Bot-Prüfung: Downloads (Netzwerk-Pool) ruhen bis dahin
        self._cond = threading.Condition()
        self._workers = 0
        self.ensure_workers()

    def ensure_workers(self) -> None:
        """Genug Worker-Threads für die aktuellen Limits starten (z.B. nach Änderung in den Einstellungen).
        Weniger Parallelität greift über die Limits in _take(), überzählige Threads warten nur."""
        with self._cond:
            needed = self.cfg.parallel_downloads + self.cfg.parallel_cuts
            while self._workers < needed:
                threading.Thread(target=self._worker, daemon=True, name=f"ytdl-worker-{self._workers}").start()
                self._workers += 1
            self._cond.notify_all()

    def known_roots(self) -> list[Path]:
        """Zielordner aller Jobs in der Liste (auch solche, die vor einer Ordner-Änderung gestartet wurden)."""
        with self._cond:
            return [Path(r) for r in {t.item.target_root for j in self.jobs for t in j.tasks} if r]

    @property
    def max_attempts(self) -> int:
        return self.cfg.max_retries + 1

    def submit(self, title: str, mode: str, items: list[Item]) -> Job:
        for item in items:  # Zielordner jetzt festhalten (wirft MissingFolder, wenn keiner eingestellt ist)
            item.target_root = item.target_root or str(self.cfg.root(item.mode))
        tasks = [Task(item=i, stage=CUT if i.start is not None else FETCH) for i in items]
        fmt = items[0].audio_format if items else ""
        job = Job(id=uuid.uuid4().hex[:8], title=title, mode=mode, tasks=tasks, max_attempts=self.max_attempts,
                  audio_format=fmt or self.cfg.audio_format)
        for task in tasks:  # für die Historie: zu welchem Download gehört der Titel
            task.job_id, task.job_title = job.id, title
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
                if task.status == Status.FAILED and (task_id is None or task.item.id == task_id):
                    task.status, task.error, task.detail = Status.WAITING, "", ""
                    task.attempt, task.next_try = 1, 0.0
                    if task.stage == CONVERT and not Path(task.workdir or "/nonexistent").exists():
                        task.stage = FETCH  # Download ist weg → von vorn
                    task.progress = STAGE_RANGE[task.stage][0]
                    self._pending.append(task)
            self._cond.notify_all()
            return job.to_dict()

    def resume(self) -> int:
        """Pause wegen Bot-Prüfung aufheben (z.B. nachdem Cookies hinterlegt wurden) – pausierte Titel sofort neu starten."""
        with self._cond:
            self.paused_until = 0.0
            count = 0
            for task in self._pending:
                if task.status == Status.PAUSED:
                    task.next_try, task.status, task.detail = 0.0, Status.WAITING, ""
                    count += 1
            self._cond.notify_all()
            return count

    def clear_finished(self) -> int:
        """Entfernt abgeschlossene Jobs aus der Liste (nur Anzeige – Dateien bleiben)."""
        with self._cond:
            before = len(self.jobs)
            self.jobs = [j for j in self.jobs if not j.finished]
            return before - len(self.jobs)

    def snapshot(self) -> list[dict]:
        with self._cond:
            return [job.to_dict() for job in self.jobs]

    def _limit(self, pool: str, now: float) -> int:
        if pool == CPU:
            return self.cfg.parallel_cuts
        if now < self.paused_until:
            return 0
        return 1 if now < self._throttle_until else self.cfg.parallel_downloads

    def _take(self) -> Task:
        """Nächste startbereite Aufgabe (Reihenfolge wie eingereiht); wartet, bis eine verfügbar ist."""
        with self._cond:
            while True:
                now = time.time()
                for task in self._pending:
                    if task.next_try <= now and self._active[task.pool] < self._limit(task.pool, now):
                        self._pending.remove(task)
                        self._active[task.pool] += 1
                        return task
                upcoming = [t.next_try for t in self._pending if t.next_try > now]
                if self.paused_until > now:
                    upcoming.append(self.paused_until)  # nach der Pause wieder aufwachen
                self._cond.wait(timeout=min(upcoming) - now if upcoming else None)

    def _worker(self) -> None:
        while True:
            task = self._take()
            pool = task.pool

            def report(status: str, pct: float, detail: str = "", task: Task = task) -> None:
                task.status, task.progress, task.detail = status, overall_progress(task.stage, pct), detail

            try:
                self._run(task, report)
                if task.status == Status.DONE:
                    self._record(task, Status.OVERWRITTEN if task.item.overwritten else Status.DONE)
            except Skipped as exc:
                task.status, task.detail, task.progress = Status.SKIPPED, str(exc), 100.0
                self._record(task, Status.SKIPPED)
            except Exception as exc:  # ein Fehler soll die Warteschlange nie stoppen
                self._failed(task, clean_error(exc))
                if task.status == Status.FAILED:
                    self._record(task, Status.FAILED)
            finally:
                with self._cond:
                    self._active[pool] -= 1
                    self._cond.notify_all()

    def _run(self, task: Task, report) -> None:
        runner = self._runners[task.stage]
        if task.stage == FETCH:
            task.workdir = str(runner(task.item, self.cfg, report))
            # Download fertig → in den CPU-Pool weiterreichen; der Netzwerk-Worker nimmt sofort den nächsten Titel
            with self._cond:
                task.stage, task.attempt, task.next_try = CONVERT, 1, 0.0
                task.status, task.progress, task.detail = Status.WAITING_FOR_CONVERT, STAGE_RANGE[CONVERT][0], ""
                self._pending.append(task)
                self._cond.notify_all()
            return
        if task.stage == CONVERT:
            task.path = str(runner(task.item, self.cfg, report, Path(task.workdir)))
        else:
            task.path = str(runner(task.item, self.cfg, report))
        task.detail = ""

    def _record(self, task: Task, result: str) -> None:
        """Abgeschlossenen Titel in die Historie schreiben – Fehler dabei dürfen den Download nicht stören."""
        if self.history is None:
            return
        try:
            fmt = audio_format(task.item, self.cfg)
            self.history.record(task.item, result, path=task.path, error=task.error, attempts=task.attempt,
                                audio_format=fmt, bitrate=self.cfg.bitrate, job_id=task.job_id,
                                job_title=task.job_title, with_cookies=cookies_active())
        except Exception:
            log.exception("Historie: Eintrag für %s nicht geschrieben", task.item.id)

    def _failed(self, task: Task, message: str) -> None:
        with self._cond:
            if task.pool == NET and is_bot_check(message):
                note_bot_check()
                task.bot_pauses += 1
                if task.bot_pauses >= MAX_BOT_PAUSES:
                    task.status, task.error, task.detail = Status.FAILED, BOT_CHECK_HINT, ""
                    return
                # Alle Downloads anhalten statt sofort weiter anzufragen – das würde die Sperre nur verlängern.
                # Kein Versuch wird verbraucht; „Jetzt fortsetzen“ hebt die Pause auf.
                self.paused_until = max(self.paused_until, time.time() + BOT_PAUSE_SECONDS)
                task.next_try = self.paused_until
                task.status, task.progress = Status.PAUSED, STAGE_RANGE[task.stage][0]
                until = time.strftime("%H:%M", time.localtime(self.paused_until))
                task.detail = f"YouTube-Bot-Prüfung – Downloads pausieren bis {until}"
                self._pending.append(task)
                self._cond.notify_all()
                return
            if task.pool == NET and is_throttled(message):
                self._throttle_until = time.time() + THROTTLE_SECONDS
            if is_permanent(message) or task.attempt >= self.max_attempts:
                task.status, task.error, task.detail = Status.FAILED, message, ""
                if task.attempt > 1 and not is_permanent(message):
                    task.error = f"{message} (nach {task.attempt} Versuchen)"
                return
            if task.stage == CONVERT and not Path(task.workdir or "/nonexistent").exists():
                task.stage = FETCH
            delay = backoff_delay(task.attempt)
            task.attempt += 1
            task.next_try = time.time() + delay
            task.status, task.progress = Status.RETRYING, STAGE_RANGE[task.stage][0]
            task.detail = f"Versuch {task.attempt}/{self.max_attempts} – letzter Fehler: {message[:160]}"
            self._pending.append(task)
            self._cond.notify_all()
