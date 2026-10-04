"""Album in einem Video: Trackgrenzen finden (Kapitel, Zeitstempel, Pausen) und zuschneiden."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

FPS = 10  # Lautstärke-Hüllkurve: 10 Werte pro Sekunde
SAMPLE_RATE = 8000
MIN_TRACK = 30.0  # Sekunden

_TS = r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})"
# "03:45 Titel", "1. 03:45 - Titel", "[03:45] Titel"
_TS_FIRST = re.compile(rf"^\s*(?:\d{{1,3}}[.)]\s*)?[\[(]?{_TS}[\])]?\s*[-–—:|.)]?\s*(.+?)\s*$")
# "1. Titel 03:45", "Titel - 03:45", "Titel (03:45)"
_TS_LAST = re.compile(rf"^\s*(?:\d{{1,3}}[.)]\s*)?(.+?)\s*[-–—|]?\s*[\[(]?{_TS}[\])]?\s*$")
_LIST_PREFIX = re.compile(r"^\s*(?:\d{1,3}[.)]|[-•*])\s*")


@dataclass
class Segment:
    start: float
    end: float
    title: str = ""

    def to_dict(self) -> dict:
        return {"start": round(self.start, 2), "end": round(self.end, 2), "title": self.title}


def _seconds(h: str | None, m: str, s: str) -> int:
    return int(h or 0) * 3600 + int(m) * 60 + int(s)


def parse_tracklist(text: str, duration: float | None = None) -> list[Segment]:
    """Liest Zeitstempel-Tracklisten aus Beschreibung/Kommentar. Leere Liste, wenn keine brauchbare gefunden."""
    entries: list[tuple[int, str]] = []
    for line in text.splitlines():
        if m := _TS_FIRST.match(line):
            h, mi, s, title = m.groups()
        elif m := _TS_LAST.match(line):
            title, h, mi, s = m.groups()
        else:
            continue
        title = _LIST_PREFIX.sub("", title.strip(" -–—|:")).strip()
        if title:
            entries.append((_seconds(h, mi, s), title))

    # Nur aufsteigende Zeitstempel behalten – filtert verirrte Zeitangaben im Fließtext
    ascending: list[tuple[int, str]] = []
    for entry in entries:
        if not ascending or entry[0] > ascending[-1][0]:
            ascending.append(entry)
    entries = ascending
    if len(entries) < 3 or entries[0][0] > 60:
        return []
    if duration and entries[-1][0] >= duration:
        return []
    if entries[0][0] > 0:
        entries[0] = (0, entries[0][1])
    end = duration or entries[-1][0] + 1
    return [
        Segment(start, entries[i + 1][0] if i + 1 < len(entries) else end, title)
        for i, (start, title) in enumerate(entries)
    ]


def parse_titles(text: str) -> list[str]:
    """Reine Titelliste (eine Zeile pro Titel, Nummerierung wird entfernt)."""
    return [t for line in text.splitlines() if (t := _LIST_PREFIX.sub("", line).strip())]


def snap(segments: list[Segment], env: np.ndarray, window: float = 3.0) -> list[Segment]:
    """Verschiebt jede Grenze auf die leiseste Stelle in ±window Sekunden (Zeitstempel sind oft gerundet)."""
    smooth = _smooth(env, 0.3)
    w = int(window * FPS)
    for prev, seg in zip(segments, segments[1:]):
        i = int(seg.start * FPS)
        lo, hi = max(1, i - w), min(len(smooth) - 1, i + w + 1)
        if lo >= hi:
            continue
        best = lo + int(np.argmin(smooth[lo:hi]))
        prev.end = seg.start = round(best / FPS, 2)
    return segments


def segments_from_chapters(chapters: list[dict], duration: float) -> list[Segment]:
    return [
        Segment(float(c["start_time"]), float(c.get("end_time") or duration), (c.get("title") or "").strip())
        for c in chapters
    ]


def envelope(audio: Path, on_progress: Callable[[float], None] | None = None) -> np.ndarray:
    """Lautstärke in dBFS, FPS Werte pro Sekunde (über ffmpeg dekodiert). on_progress bekommt die
    bisher verarbeiteten Sekunden."""
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(audio), "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "s16le", "-"],
        stdout=subprocess.PIPE,
    )
    frame = SAMPLE_RATE // FPS
    values: list[np.ndarray] = []
    rest = np.empty(0, dtype=np.float32)
    assert proc.stdout is not None
    while chunk := proc.stdout.read(frame * 2 * FPS * 60):  # eine Minute pro Durchgang
        samples = np.concatenate([rest, np.frombuffer(chunk, dtype="<i2").astype(np.float32) / 32768])
        usable = len(samples) // frame * frame
        rms = np.sqrt(np.mean(samples[:usable].reshape(-1, frame) ** 2, axis=1))
        values.append(rms)
        rest = samples[usable:]
        if on_progress:
            on_progress(sum(len(v) for v in values) / FPS)
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg konnte das Audio nicht lesen")
    rms = np.concatenate(values) if values else np.zeros(1)
    return 20 * np.log10(np.maximum(rms, 1e-5))


def _smooth(env: np.ndarray, seconds: float) -> np.ndarray:
    width = max(1, int(seconds * FPS))
    return np.convolve(env, np.ones(width) / width, mode="same")


def _center_of_quiet(env: np.ndarray, index: int, tolerance_db: float = 4.0) -> int:
    """Verschiebt einen Schnittpunkt in die Mitte der umgebenden leisen Stelle."""
    level = env[index] + tolerance_db
    left = right = index
    while left > 0 and env[left - 1] <= level and index - left < 10 * FPS:
        left -= 1
    while right < len(env) - 1 and env[right + 1] <= level and right - index < 10 * FPS:
        right += 1
    return (left + right) // 2


def detect_boundaries(
    env: np.ndarray,
    count: int | None = None,
    min_pause: float = 1.0,
    sensitivity_db: float = 25.0,
    min_track: float = MIN_TRACK,
) -> list[float]:
    """Findet Schnittpunkte (Sekunden, ohne 0 und Ende).

    - count gesetzt: die count-1 leisesten Stellen mit Mindestabstand min_track (funktioniert auch bei Überblendungen)
    - sonst: alle Pausen, die mind. min_pause lang und sensitivity_db leiser als der Median sind
    """
    if len(env) < 2 * min_track * FPS:
        return []
    smooth = _smooth(env, 1.0)
    gap = int(min_track * FPS)
    edge = int(min(10.0, min_track / 2) * FPS)

    if count and count > 1:
        order = np.argsort(smooth[edge:-edge]) + edge
        chosen: list[int] = []
        for idx in order:
            if all(abs(idx - c) >= gap for c in chosen):
                chosen.append(int(idx))
                if len(chosen) == count - 1:
                    break
        cuts = sorted(_center_of_quiet(env, c) for c in chosen)
        return [c / FPS for c in cuts]

    threshold = np.median(env) - sensitivity_db
    quiet = env < threshold
    cuts: list[tuple[int, float]] = []  # (Position, Tiefe)
    start = None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) >= min_pause * FPS and start > edge and i < len(env) - edge:
                cuts.append(((start + i) // 2, float(env[start:i].mean())))
            start = None

    # Zu kurze Titel vermeiden: bei zu nahen Schnitten den leiseren behalten
    result: list[tuple[int, float]] = []
    for pos, depth in cuts:
        if result and pos - result[-1][0] < gap:
            if depth < result[-1][1]:
                result[-1] = (pos, depth)
            continue
        result.append((pos, depth))
    return [pos / FPS for pos, _ in result]


def segments_from_boundaries(cuts: list[float], duration: float) -> list[Segment]:
    points = [0.0, *cuts, duration]
    return [Segment(points[i], points[i + 1]) for i in range(len(points) - 1)]


def peaks(env: np.ndarray, points: int = 1500) -> list[float]:
    """Verkleinerte Hüllkurve (0..1) für die Wellenform-Anzeige."""
    if len(env) == 0:
        return []
    size = max(1, int(np.ceil(len(env) / points)))
    padded = np.pad(env, (0, (-len(env)) % size), constant_values=env.min())
    maxima = padded.reshape(-1, size).max(axis=1)
    floor = max(float(np.percentile(env, 2)), -70.0)
    scaled = np.clip((maxima - floor) / (float(env.max()) - floor + 1e-9), 0, 1)
    return [round(float(v), 3) for v in scaled]


def cut(source: Path, start: float, end: float | None, target: Path, bitrate: int) -> None:
    """Schneidet einen Abschnitt heraus (ohne Metadaten der Quelle).

    Ziel .mp3 → MP3 mit `bitrate`; Ziel .m4a → aus M4A-Quelle ohne Neukodierung, sonst AAC 256 kbit/s."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}"]
    if end:
        cmd += ["-to", f"{end:.2f}"]
    if target.suffix.lower() == ".m4a":
        codec = ["-c:a", "copy"] if source.suffix.lower() in (".m4a", ".mp4") else ["-c:a", "aac", "-b:a", "256k"]
    else:
        codec = ["-c:a", "libmp3lame", "-b:a", f"{bitrate}k"]
    cmd += ["-i", str(source), "-vn", "-map_metadata", "-1", *codec, str(target)]
    subprocess.run(cmd, check=True, capture_output=True)
