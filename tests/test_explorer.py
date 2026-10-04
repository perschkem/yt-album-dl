from pathlib import Path

from ytdl import explorer


def test_is_allowed(tmp_path):
    root = tmp_path / "Musik"
    (root / "A").mkdir(parents=True)
    assert explorer.is_allowed(root / "A" / "x.mp3", [root])
    assert explorer.is_allowed(root, [root])
    assert not explorer.is_allowed(tmp_path / "anderes" / "x.mp3", [root])
    assert not explorer.is_allowed(root / ".." / "geheim.txt", [root])


def test_open_selects_file_in_windows_explorer(tmp_path, monkeypatch):
    f = tmp_path / "a b.mp3"
    f.write_bytes(b"x")
    calls = []
    monkeypatch.setattr(explorer.shutil, "which", lambda name: "/mnt/c/Windows/explorer.exe" if name == "explorer.exe" else None)
    monkeypatch.setattr(explorer.subprocess, "Popen", lambda args, **kw: calls.append(args))
    explorer.open_in_file_manager(f)
    assert calls[0][0].endswith("explorer.exe") and calls[0][1].startswith("/select,")
