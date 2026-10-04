"""Download-Historie: eine JSON-Zeile pro Titel in data/history.jsonl (liegt unter data/, also nicht im Repo)."""

from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
from pathlib import Path

from .metadata import Item
from .paths import to_windows_path

FINISHED, SKIPPED, OVERWRITTEN, FAILED = "fertig", "übersprungen", "überschrieben", "fehler"
_TAG_KEYS = ("artist", "title", "album", "album_artist", "track_no", "track_total", "year", "date", "genre")


class History:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "history.jsonl"
        self._lock = threading.Lock()

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
            "win_path": to_windows_path(file) if file else "",
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
        if not self.path.exists():
            return []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        entries = []
        for line in lines:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # kaputte Zeile (z.B. nach Absturz beim Schreiben) überspringen
        entries.reverse()  # neueste zuerst
        return entries

    def query(self, q: str = "", mode: str = "", result: str = "", since: float | None = None,
              limit: int = 50, offset: int = 0) -> dict:
        words = q.lower().split()
        matches = []
        for entry in self._all():
            if mode and entry.get("mode") != mode:
                continue
            if result and entry.get("result") != result:
                continue
            if since and entry.get("ts", 0) < since:
                continue
            if words:
                haystack = " ".join(str(v) for v in (*entry.get("tags", {}).values(), entry.get("url"),
                                                      entry.get("path"), entry.get("source_title"))).lower()
                if not all(w in haystack for w in words):
                    continue
            matches.append(entry)
        page = matches[offset:offset + limit]
        for entry in page:
            entry["exists"] = bool(entry.get("path")) and Path(entry["path"]).exists()
        return {"total": len(matches), "entries": page}

    def query_groups(self, q: str = "", mode: str = "", result: str = "", since: float | None = None,
                     limit: int = 20, offset: int = 0) -> dict:
        """Wie query(), aber nach Download (Job) gruppiert – neueste Downloads zuerst, Titel in Job-Reihenfolge.
        Ältere Einträge ohne Job-ID bilden jeweils eine eigene Gruppe."""
        entries = self.query(q=q, mode=mode, result=result, since=since, limit=10**9)["entries"]
        groups: dict[str, dict] = {}
        for i, e in enumerate(entries):  # neueste zuerst
            key = e.get("job_id") or f"einzeln-{i}"
            group = groups.get(key)
            if group is None:
                t = e.get("tags", {})
                group = groups[key] = {
                    "id": key,
                    "title": e.get("job_title") or t.get("album") or " - ".join(filter(None, (t.get("artist"), t.get("title")))),
                    "mode": e.get("mode"), "format": e.get("format"), "ts": e.get("ts", 0), "entries": [],
                }
            group["entries"].append(e)
        result_groups = []
        for group in groups.values():
            group["entries"].sort(key=lambda e: (e.get("tags", {}).get("track_no") or 0, e.get("ts", 0)))
            counts: dict[str, int] = {}
            for e in group["entries"]:
                counts[e["result"]] = counts.get(e["result"], 0) + 1
            existing = [e["path"] for e in group["entries"] if e.get("exists")]
            folder = existing[0] if len(existing) == 1 else (
                os.path.commonpath([str(Path(p).parent) for p in existing]) if existing else "")
            group.update(count=len(group["entries"]), counts=counts, folder=folder,
                         win_folder=to_windows_path(Path(folder)) if folder else "")
            result_groups.append(group)
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
        return count

    def to_csv(self, **filters) -> str:
        rows = self.query(limit=10**9, **filters)["entries"]
        out = io.StringIO()
        columns = ["Zeit", "Ergebnis", "Modus", "Format", "Interpret", "Titel", "Album", "Albuminterpret",
                   "Nr.", "Jahr", "Genre", "Cover", "URL", "Start", "Ende", "Pfad", "Fehler"]
        writer = csv.writer(out, delimiter=";")
        writer.writerow(columns)
        for e in rows:
            t = e.get("tags", {})
            writer.writerow([
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.get("ts", 0))), e.get("result"), e.get("mode"),
                e.get("format"), t.get("artist", ""), t.get("title", ""), t.get("album", ""),
                t.get("album_artist", ""), t.get("track_no", ""), t.get("year", "") or t.get("date", ""),
                t.get("genre", ""), e.get("cover"), e.get("url"), e.get("start") or "", e.get("end") or "",
                e.get("win_path") or e.get("path"), e.get("error"),
            ])
        return out.getvalue()
