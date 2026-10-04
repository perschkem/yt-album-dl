"""Dateien/Ordner im Dateimanager öffnen – unter WSL im Windows-Explorer, auf dem Mac im Finder, sonst xdg-open."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .i18n import t
from .paths import to_windows_path


def is_allowed(path: Path, roots: list[Path]) -> bool:
    """Nur Pfade innerhalb der Zielordner (verhindert, dass beliebige Pfade geöffnet werden)."""
    resolved = path.resolve()
    return any(resolved == root.resolve() or resolved.is_relative_to(root.resolve()) for root in roots)


def _windows_path(path: Path) -> str:
    if shutil.which("wslpath"):
        result = subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return to_windows_path(path)


def open_in_file_manager(path: Path) -> str:
    """Öffnet den Ordner; ist `path` eine Datei, wird sie im Explorer markiert. Gibt den geöffneten Pfad zurück."""
    if not path.exists():
        raise FileNotFoundError(t("errors.not_found", path=path))
    explorer = shutil.which("explorer.exe")
    if explorer:
        win = _windows_path(path)
        args = [explorer, f"/select,{win}"] if path.is_file() else [explorer, win]
        # explorer.exe liefert auch bei Erfolg Exit-Code 1 → Ergebnis nicht auswerten
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return win
    if sys.platform == "darwin":
        # macOS: Finder öffnen, Datei markieren (-R)
        args = ["open", "-R", str(path)] if path.is_file() else ["open", str(path)]
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(path)
    folder = path.parent if path.is_file() else path
    if not shutil.which("xdg-open"):
        raise RuntimeError(t("errors.no_file_manager"))
    subprocess.Popen(["xdg-open", str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(folder)
