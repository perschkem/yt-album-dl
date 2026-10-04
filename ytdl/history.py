"""Download-Historie: eine JSON-Zeile pro Titel in data/history.jsonl (liegt unter data/, also nicht im Repo)."""

from __future__ import annotations

import csv
import io
import json
import threading
import time
from collections import Counter
from pathlib import Path

from .metadata import Item
from .paths import common_folder, win_path

_TAG_KEYS = ("artist", "title", "album", "album_artist", "track_no", "track_total", "year", "date", "genre")


class History:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "history.jsonl"
        self._lock = threading.Lock()
        self._cache: tuple[tuple[int, int], list[dict]] | None = None  # ((mtime_ns, Größe), Einträge)

    def record(self, item: Item, result: str, *, path: str = "", error: str = "", attempts: int = 1,
               audio_format: str = "", bitrate: int | None = None, job_id: str = "", job_title: str = "",
               with_cookies: bool = False) -> dict:
        file = Path(path) if path else None
        entry = {
            "ts": time.time(),
            "job_id": job_id,
            "job_title": job_title,
            "result": result,
            "mode": item.mode,
            "format": audio_format,
            "bitrate": bitrate if audio_format == "mp3" else None,
            "url": item.url,
            "video_id": item.source_id or item.id,
            "source_title": item.source_title,
            "start": item.start,
            "end": item.end,
            "boundary_source": item.boundary_source,
            "path": path,
            "win_path": win_path(file),
            "size": file.stat().st_size if file and file.exists() else None,
            "tags": {k: getattr(item, k) for k in _TAG_KEYS if getattr(item, k) not in (None, "")},
            "cover": "eigene URL" if item.cover_url else "YouTube-Vorschaubild",
            "cover_url": item.cover_url,
            "error": error,
            "attempts": attempts,
            # nach einer YouTube-Bot-Prüfung mit hinterlegter Anmeldung (Cookies) geladen
            "with_cookies": with_cookies,
        }
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return entry

    def _all(self) -> list[dict]:
        """Alle Einträge, neueste zuerst. Zwischengespeichert, bis sich die Datei ändert (Größe/Zeitstempel)."""
        with self._lock:
            try:
                stat = self.path.stat()
            except FileNotFoundError:
                self._cache = None
                return []
            key = (stat.st_mtime_ns, stat.st_size)
            if self._cache is None or self._cache[0] != key:
                self._cache = (key, self._parse(self.path.read_text(encoding="utf-8")))
            # Kopien (auch der Tags) – query() ergänzt "exists", Aufrufer dürfen die Einträge verändern
            return [{**e, "tags": dict(e.get("tags", {}))} for e in self._cache[1]]

    @staticmethod
    def _parse(text: str) -> list[dict]:
        entries = []
        for line in text.splitlines():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # kaputte Zeile (z.B. nach Absturz beim Schreiben) überspringen
        entries.reverse()  # neueste zuerst
        return entries

    def _matching(self, q: str = "", mode: str = "", result: str = "", since: float | None = None) -> list[dict]:
        """Einträge, die zu den Filtern passen; bei der Suche müssen alle Wörter vorkommen."""
        words = q.lower().split()

        def matches(entry: dict) -> bool:
            if (mode and entry.get("mode") != mode) or (result and entry.get("result") != result):
                return False
            if since and entry.get("ts", 0) < since:
                return False
            if not words:
                return True
            haystack = " ".join(str(v) for v in (*entry.get("tags", {}).values(), entry.get("url"),
                                                  entry.get("path"), entry.get("source_title"))).lower()
            return all(w in haystack for w in words)

        return [e for e in self._all() if matches(e)]

    @staticmethod
    def _mark_existing(entries: list[dict]) -> list[dict]:
        for entry in entries:
            entry["exists"] = bool(entry.get("path")) and Path(entry["path"]).exists()
        return entries

    def query(self, q: str = "", mode: str = "", result: str = "", since: float | None = None,
              limit: int = 50, offset: int = 0) -> dict:
        matches = self._matching(q, mode, result, since)
        return {"total": len(matches), "entries": self._mark_existing(matches[offset:offset + limit])}

    def query_groups(self, q: str = "", mode: str = "", result: str = "", since: float | None = None,
                     limit: int = 20, offset: int = 0) -> dict:
        """Wie query(), aber nach Download (Job) gruppiert – neueste Downloads zuerst, Titel in Job-Reihenfolge.
        Ältere Einträge ohne Job-ID bilden jeweils eine eigene Gruppe."""
        entries = self._mark_existing(self._matching(q, mode, result, since))
        groups: dict[str, dict] = {}
        for i, e in enumerate(entries):  # neueste zuerst
            key = e.get("job_id") or f"einzeln-{i}"
            if key not in groups:
                t = e.get("tags", {})
                groups[key] = {
                    "id": key,
                    "title": e.get("job_title") or t.get("album") or " - ".join(filter(None, (t.get("artist"), t.get("title")))),
                    "mode": e.get("mode"), "format": e.get("format"), "ts": e.get("ts", 0), "entries": [],
                }
            groups[key]["entries"].append(e)
        for group in groups.values():
            group["entries"].sort(key=lambda e: (e.get("tags", {}).get("track_no") or 0, e.get("ts", 0)))
            existing = [e["path"] for e in group["entries"] if e.get("exists")]
            folder = existing[0] if len(existing) == 1 else common_folder(existing)  # einzelne Datei: markieren
            group.update(count=len(group["entries"]), counts=dict(Counter(e["result"] for e in group["entries"])),
                         folder=folder, win_folder=win_path(folder))
        result_groups = list(groups.values())
        return {"total": len(result_groups), "entries_total": len(entries),
                "groups": result_groups[offset:offset + limit]}

    def knows_path(self, path: Path) -> bool:
        """Für „Im Ordner öffnen“: Pfade aus der Historie dürfen geöffnet werden (auch aus früheren Zielordnern)."""
        target = str(path)
        return any(e.get("path") == target or (e.get("path") and str(Path(e["path"]).parent) == target)
                   for e in self._all())

    def clear(self) -> int:
        count = len(self._all())
        with self._lock:
            self.path.unlink(missing_ok=True)
            self._cache = None
        return count

    def to_csv(self, **filters) -> str:
        out = io.StringIO()
        writer = csv.writer(out, delimiter=";")
        writer.writerow([header for header, _ in CSV_COLUMNS])
        for entry in self._matching(**filters):
            tags = entry.get("tags", {})
            writer.writerow([value(entry, tags) for _, value in CSV_COLUMNS])
        return out.getvalue()


def _tag(key: str):
    return lambda e, t: t.get(key, "")


# (Spaltenkopf, Wert aus Eintrag und Tags) – Kopf und Wert stehen zusammen, damit nichts verrutscht
CSV_COLUMNS = [
    ("Zeit", lambda e, t: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.get("ts", 0)))),
    ("Ergebnis", lambda e, t: e.get("result")),
    ("Modus", lambda e, t: e.get("mode")),
    ("Format", lambda e, t: e.get("format")),
    ("Interpret", _tag("artist")),
    ("Titel", _tag("title")),
    ("Album", _tag("album")),
    ("Albuminterpret", _tag("album_artist")),
    ("Nr.", _tag("track_no")),
    ("Jahr", lambda e, t: t.get("year", "") or t.get("date", "")),
    ("Genre", _tag("genre")),
    ("Cover", lambda e, t: e.get("cover")),
    ("URL", lambda e, t: e.get("url")),
    ("Start", lambda e, t: e.get("start") or ""),
    ("Ende", lambda e, t: e.get("end") or ""),
    ("Pfad", lambda e, t: e.get("win_path") or e.get("path")),
    ("Fehler", lambda e, t: e.get("error")),
]
