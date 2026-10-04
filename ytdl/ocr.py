"""Text im Videobild lesen (OCR): eingeblendete Tracklisten und wechselnde Titeleinblendungen."""

from __future__ import annotations

import io
import re
import subprocess
from collections import Counter
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from .split import Segment, parse_tracklist

_TIMESTAMP = re.compile(r"\d{1,2}:\d{2}")


@lru_cache(maxsize=1)
def _engine():
    from rapidocr import RapidOCR  # lädt Modelle – erst bei Bedarf

    return RapidOCR()


def read_lines(image: Image.Image) -> list[str]:
    """OCR eines Bildes; Zeilen von oben nach unten (bei gleicher Höhe links nach rechts)."""
    result = _engine()(np.asarray(image.convert("RGB")))
    if not result.txts:
        return []
    boxes = [(float(b[0][1]), float(b[0][0]), t) for b, t in zip(result.boxes, result.txts)]
    boxes.sort(key=lambda b: (round(b[0] / 12), b[1]))
    # Kästchen auf gleicher Zeile zusammenfügen (z.B. "[00:05:48]" und "02. Titel")
    lines: list[tuple[float, list[str]]] = []
    for top, _, text in boxes:
        if lines and abs(lines[-1][0] - top) < 10:
            lines[-1][1].append(text)
        else:
            lines.append((top, [text]))
    return [" ".join(parts).strip() for _, parts in lines]


def grab_frame(source: str, seconds: float, headers: dict | None = None, height: int = 720) -> Image.Image | None:
    """Holt ein einzelnes Standbild per ffmpeg (aus lokaler Datei oder Stream-URL)."""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{seconds:.2f}"]
    if headers and source.startswith("http"):
        cmd += ["-headers", "".join(f"{k}: {v}\r\n" for k, v in headers.items())]
    cmd += ["-i", source, "-frames:v", "1", "-vf", f"scale=-2:'min({height},ih)'", "-f", "image2pipe", "-vcodec", "png", "-"]
    proc = subprocess.run(cmd, capture_output=True, timeout=90)
    if proc.returncode != 0 or not proc.stdout:
        return None
    return Image.open(io.BytesIO(proc.stdout))


def video_stream(info: dict, max_height: int = 720) -> tuple[str, dict] | None:
    """Beste Videospur bis max_height (URL + nötige HTTP-Header) aus den yt-dlp-Infos."""
    formats = [
        f for f in info.get("formats") or []
        if f.get("vcodec") not in (None, "none") and f.get("url") and (f.get("height") or 0) <= max_height
        and f.get("protocol", "https").startswith("http")
    ]
    if not formats:
        return None
    best = max(formats, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
    return best["url"], best.get("http_headers") or {}


def tracklist_from_frames(info: dict, duration: float, samples: int = 6,
                          on_progress: Callable[[int, int, int], None] | None = None
                          ) -> tuple[list[Segment], list[str]]:
    """Sucht eine eingeblendete Trackliste mit Zeitstempeln in einigen Standbildern.

    Liefert (Segmente, übrige Textzeilen des besten Bildes – z.B. Interpretname als Hinweis).
    on_progress(bild, von, gefundene_zeilen_mit_text) wird nach jedem Bild aufgerufen.
    """
    stream = video_stream(info)
    if not stream:
        return [], []
    url, headers = stream
    best: tuple[list[Segment], list[str]] = ([], [])
    for i in range(samples):
        t = duration * (0.02 + 0.96 * i / max(1, samples - 1))
        frame = grab_frame(url, t, headers)
        lines = read_lines(frame) if frame is not None else []
        if on_progress:
            on_progress(i + 1, samples, len(lines))
        if not lines:
            continue
        segments = parse_tracklist("\n".join(lines), duration)
        if len(segments) > len(best[0]):
            others = [line for line in lines if not _TIMESTAMP.search(line)]
            best = (segments, others)
            if len(segments) >= 3:
                break  # Trackliste gefunden – restliche Bilder nicht nötig
    return best


def overlay_titles(video: Path, duration: float, step: float = 10.0,
                   on_progress: Callable[[int, int], None] | None = None) -> list[Segment]:
    """Liest wechselnde Titeleinblendungen: alle `step` Sekunden ein Bild, Textwechsel = neuer Titel."""
    readings: list[tuple[float, list[str]]] = []
    total = max(1, int(duration // step) + 1)
    t = 0.0
    while t < duration:
        frame = grab_frame(str(video), t, height=480)
        readings.append((t, read_lines(frame) if frame else []))
        if on_progress:
            on_progress(len(readings), total)
        t += step
    if not readings:
        return []

    # Text, der fast immer zu sehen ist (Logo, Kanalname), ist kein Titel
    counts = Counter(line for _, lines in readings for line in set(lines))
    static = {line for line, n in counts.items() if n > 0.6 * len(readings)}

    segments: list[Segment] = []
    for t, lines in readings:
        text = " – ".join(line for line in lines if line not in static and len(line) > 2)
        if not text:
            continue
        if segments and _similar(segments[-1].title, text):
            segments[-1].end = t + step
            continue
        segments.append(Segment(t, t + step, text))

    # Lücken schließen: jeder Titel läuft bis zum nächsten
    for current, following in zip(segments, segments[1:]):
        current.end = following.start
    if segments:
        segments[0].start = 0.0
        segments[-1].end = duration
    return segments if len(segments) >= 2 else []


def _similar(a: str, b: str) -> bool:
    """Grober Vergleich, der kleine OCR-Abweichungen toleriert."""
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())  # noqa: E731
    x, y = norm(a), norm(b)
    if not x or not y:
        return False
    common = sum((Counter(x) & Counter(y)).values())
    return common / max(len(x), len(y)) > 0.8
