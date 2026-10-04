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
from .auth import BOT_CHECK_HINT, is_bot_check, youtube
from .config import Config
from .downloader import convert, fetch
from .errors import clean_error
from .history import History
from .library import Skipped, audio_format
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
NEXT_STAGE = {FETCH: CONVERT}  # nach dem Download wird konvertiert; Konvertieren und Schneiden sind die letzte Stufe
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

    # ---------- Zustandsübergänge ----------

    def report(self, status: str, pct: float, detail: str = "") -> None:
        """Fortschritt aus dem Runner (pct bezieht sich auf die aktuelle Stufe)."""
        self.status, self.progress, self.detail = status, overall_progress(self.stage, pct), detail

    def requeue(self, status: str, next_try: float = 0.0, detail: str = "") -> None:
        """Wartet wieder auf einen Worker – der Balken steht am Anfang der aktuellen Stufe."""
        self.status, self.detail, self.next_try = status, detail, next_try
        self.progress = STAGE_RANGE[self.stage][0]

    def restart_stage(self) -> None:
        """Konvertieren braucht den Download; ist das Arbeitsverzeichnis weg, beginnt der Titel von vorn."""
        if self.stage == CONVERT and not (self.workdir and Path(self.workdir).exists()):
            self.stage = FETCH

    def advance(self, workdir: str) -> None:
        """Stufe geschafft → nächste Stufe mit frischem Versuchszähler."""
        self.workdir, self.stage, self.attempt = workdir, NEXT_STAGE[self.stage], 1
        self.requeue(Status.WAITING_FOR_CONVERT)

    def finish(self, path: str) -> None:
        self.path, self.detail = path, ""

    def fail(self, message: str) -> None:
        self.status, self.error, self.detail = Status.FAILED, message, ""

    def skip(self, reason: str) -> None:
        self.status, self.detail, self.progress = Status.SKIPPED, reason, 100.0

    def reset_for_retry(self) -> None:
        """Manuell „Erneut versuchen“: Fehler vergessen, Versuche von vorn zählen."""
        self.error, self.attempt = "", 1
        self.restart_stage()
        self.requeue(Status.WAITING)

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
                    task.reset_for_retry()
                    self._enqueue(task)
            return job.to_dict()

    def resume(self) -> int:
        """Pause wegen Bot-Prüfung aufheben (z.B. nachdem Cookies hinterlegt wurden) – pausierte Titel sofort neu starten."""
        with self._cond:
            self.paused_until = 0.0
            paused = [t for t in self._pending if t.status == Status.PAUSED]
            for task in paused:
                task.requeue(Status.WAITING)
            self._cond.notify_all()
            return len(paused)

    def clear_finished(self) -> int:
        """Entfernt abgeschlossene Jobs aus der Liste (nur Anzeige – Dateien bleiben)."""
        with self._cond:
            before = len(self.jobs)
            self.jobs = [j for j in self.jobs if not j.finished]
            return before - len(self.jobs)

    def snapshot(self) -> list[dict]:
        with self._cond:
            return [job.to_dict() for job in self.jobs]

    def _enqueue(self, task: Task) -> None:
        """Aufgabe (wieder) einreihen – nur mit gehaltenem self._cond aufrufen."""
        self._pending.append(task)
        self._cond.notify_all()

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
            try:
                self._run(task)
                if task.status == Status.DONE:
                    self._record(task, Status.OVERWRITTEN if task.item.overwritten else Status.DONE)
            except Skipped as exc:
                task.skip(str(exc))
                self._record(task, Status.SKIPPED)
            except Exception as exc:  # noqa: BLE001 – ein Fehler soll die Warteschlange nie stoppen
                self._failed(task, clean_error(exc))
                if task.status == Status.FAILED:
                    self._record(task, Status.FAILED)
            finally:
                with self._cond:
                    self._active[pool] -= 1
                    self._cond.notify_all()

    def _run(self, task: Task) -> None:
        """Alle Runner haben dieselbe Signatur (item, cfg, report, workdir) und liefern einen Pfad: das
        Arbeitsverzeichnis für die nächste Stufe bzw. die fertige Datei."""
        workdir = Path(task.workdir) if task.workdir else None
        result = str(self._runners[task.stage](task.item, self.cfg, task.report, workdir))
        if task.stage in NEXT_STAGE:
            # Download fertig → in den CPU-Pool weiterreichen; der Netzwerk-Worker nimmt sofort den nächsten Titel
            with self._cond:
                task.advance(result)
                self._enqueue(task)
        else:
            task.finish(result)

    def _record(self, task: Task, result: str) -> None:
        """Abgeschlossenen Titel in die Historie schreiben – Fehler dabei dürfen den Download nicht stören."""
        if self.history is None:
            return
        try:
            fmt = audio_format(task.item, self.cfg)
            self.history.record(task.item, result, path=task.path, error=task.error, attempts=task.attempt,
                                audio_format=fmt, bitrate=self.cfg.bitrate, job_id=task.job_id,
                                job_title=task.job_title, with_cookies=youtube.cookies_active())
        except Exception:
            log.exception("Historie: Eintrag für %s nicht geschrieben", task.item.id)

    def _failed(self, task: Task, message: str) -> None:
        with self._cond:
            if task.pool == NET and is_bot_check(message):
                youtube.note_bot_check()
                task.bot_pauses += 1
                if task.bot_pauses >= MAX_BOT_PAUSES:
                    task.fail(BOT_CHECK_HINT)
                    return
                # Alle Downloads anhalten statt sofort weiter anzufragen – das würde die Sperre nur verlängern.
                # Kein Versuch wird verbraucht; „Jetzt fortsetzen“ hebt die Pause auf.
                self.paused_until = max(self.paused_until, time.time() + BOT_PAUSE_SECONDS)
                until = time.strftime("%H:%M", time.localtime(self.paused_until))
                task.requeue(Status.PAUSED, self.paused_until, f"YouTube-Bot-Prüfung – Downloads pausieren bis {until}")
                self._enqueue(task)
                return
            if task.pool == NET and is_throttled(message):
                self._throttle_until = time.time() + THROTTLE_SECONDS
            permanent = is_permanent(message)
            if permanent or task.attempt >= self.max_attempts:
                task.fail(message if permanent or task.attempt == 1 else f"{message} (nach {task.attempt} Versuchen)")
                return
            task.restart_stage()
            delay = backoff_delay(task.attempt)
            task.attempt += 1
            task.requeue(Status.RETRYING, time.time() + delay,
                         f"Versuch {task.attempt}/{self.max_attempts} – letzter Fehler: {message[:160]}")
            self._enqueue(task)
