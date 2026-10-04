"""Ablage in der Musik-/Podcast-Bibliothek: Zielpfad, Konflikte, Archiv – und das Fertigstellen eines Titels
(Cover wählen, taggen, ablegen)."""

from __future__ import annotations

import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from .config import AUDIO_FORMATS, Config
from .covers import CoverError, fetch_cover
from .i18n import t
from .metadata import Item
from .paths import target_path, win_path
from .status import Status
from .tagger import write_tags

ProgressCallback = Callable[..., None]  # (Status, Prozent 0..100, Detailtext="")

KEEP_BOTH, OVERWRITE, SKIP = "keep_both", "overwrite", "skip"
CONFLICT_CHOICES = (KEEP_BOTH, OVERWRITE, SKIP)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
_PARTIAL_SUFFIXES = (".part", ".ytdl")
_PLACE_LOCK = threading.Lock()


class Skipped(Exception):
    """Zieldatei existiert und der Titel soll übersprungen werden."""


def no_progress(status: str, pct: float, detail: str = "") -> None:
    pass


def downloaded_file(folder: Path, stem: str, image: bool = False) -> Path | None:
    """Fertig geladene Datei `<stem>.*` im Ordner – die Audio-/Videospur (image=False) oder das gleichnamige
    Vorschaubild (image=True). Halbfertige Downloads (.part, .ytdl) zählen nicht."""
    for path in sorted(folder.glob(f"{stem}.*")):
        if path.name.endswith(_PARTIAL_SUFFIXES):
            continue
        if (path.suffix.lower() in IMAGE_SUFFIXES) == image:
            return path
    return None


class Archive:
    """Merkt sich bereits heruntergeladene Video-IDs je Modus (data/archive-<modus>.txt)."""

    def __init__(self, data_dir: Path, mode: str):
        self.path = data_dir / f"archive-{mode}.txt"
        self._lock = threading.Lock()

    def ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        return {line.strip() for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()}

    def add(self, video_id: str) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(video_id + "\n")


def audio_format(item: Item, cfg: Config) -> str:
    return item.audio_format if item.audio_format in AUDIO_FORMATS else cfg.audio_format


def final_path(item: Item, cfg: Config) -> Path:
    """Zielpfad inkl. Endung des gewählten Formats (ohne Kollisionsbehandlung)."""
    root = Path(item.target_root) if item.target_root else cfg.root(item.mode)
    return target_path(item, root).with_suffix(f".{audio_format(item, cfg)}")


def _unique(path: Path) -> Path:
    """Hängt ' (2)', ' (3)' … an, falls die Datei schon existiert – es wird nie etwas überschrieben."""
    if not path.exists():
        return path
    n = 2
    while (candidate := path.with_name(f"{path.stem} ({n}){path.suffix}")).exists():
        n += 1
    return candidate


def place(src: Path, item: Item, cfg: Config) -> Path:
    """Verschiebt die fertige Datei an ihren Zielort – je nach item.on_conflict:
    keep_both → „… (2)“, overwrite → ersetzen, skip → Skipped. Gesperrt, damit parallele Titel
    mit gleichem Namen nicht beide denselben freien Dateinamen wählen."""
    target = final_path(item, cfg)
    with _PLACE_LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if item.on_conflict == SKIP:
                raise Skipped(t("library.skipped_exists", name=target.name))
            if item.on_conflict == OVERWRITE:
                # erst neben das Ziel kopieren, dann atomar ersetzen – bei Fehlern bleibt die alte Datei
                staging = target.with_name(f".{target.stem}.neu{target.suffix}")
                shutil.move(str(src), staging)
                staging.replace(target)
                item.overwritten = True
                return target
            target = _unique(target)
        shutil.move(str(src), target)
    return target


def conflicts(items: list[Item], cfg: Config) -> list[dict]:
    """Titel, deren Zieldatei schon existiert – für den Dialog in der Oberfläche."""
    found = []
    for item in items:
        path = final_path(item, cfg)
        if path.exists():
            stat = path.stat()
            found.append({"id": item.id, "label": item.label, "path": str(path), "win_path": win_path(path),
                          "size": stat.st_size, "modified": stat.st_mtime})
    return found


def choose_cover(item: Item, cfg: Config, thumbnail: Path | None, report: ProgressCallback) -> tuple[Path | None, bool]:
    """Eigenes Cover (falls angegeben und ladbar), sonst das YouTube-Vorschaubild (quadratisch zugeschnitten)."""
    if item.cover_url:
        try:
            return fetch_cover(item.cover_url, cfg.data_dir / "covers"), item.cover_crop
        except CoverError as exc:
            report(Status.TAGGING, 85.0, t("library.cover_fallback", error=exc))
    return thumbnail, True


def finish_track(audio: Path, item: Item, cfg: Config, thumbnail: Path | None, report: ProgressCallback,
                 tag_progress: float) -> Path:
    """Fertig kodierte Datei taggen, ablegen und im Archiv vermerken (gemeinsam für Download und Album-Schnitt).
    Album-Schnitte werden mit der ID des Quellvideos archiviert."""
    report(Status.TAGGING, tag_progress)
    cover, crop = choose_cover(item, cfg, thumbnail, report)
    write_tags(audio, item, cover, crop)
    target = place(audio, item, cfg)
    Archive(cfg.data_dir, item.mode).add(item.source_id or item.id)
    report(Status.DONE, 100.0)
    return target
