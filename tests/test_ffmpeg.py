import subprocess
from pathlib import Path

import pytest

from ytdl import ffmpeg, ocr, split, ytdlp
from ytdl.config import Config


@pytest.fixture()
def configured(tmp_path):
    folder = tmp_path / "ffmpeg-bin"
    folder.mkdir()
    (folder / "ffmpeg").write_text("#!/bin/sh\n")
    ffmpeg.configure(str(folder))
    yield folder
    ffmpeg.configure(None)


def cfg_with(location):
    return Config(musik_dir=None, podcast_dir=None, data_dir=Path("/tmp"), bitrate=320, host="", port=0,
                  ffmpeg_location=location)


def test_executable_from_folder_file_or_path(tmp_path):
    assert ffmpeg.executable() == "ffmpeg"
    assert ffmpeg.executable(str(tmp_path)) == str(tmp_path / "ffmpeg")  # Ordner
    exe = tmp_path / "mein-ffmpeg"
    exe.write_text("")
    assert ffmpeg.executable(str(exe)) == str(exe)  # Datei


def test_available(tmp_path, configured):
    assert ffmpeg.ffmpeg_available(cfg_with(str(configured)))
    assert ffmpeg.ffmpeg_available(cfg_with(str(configured / "ffmpeg")))
    assert not ffmpeg.ffmpeg_available(cfg_with(str(tmp_path / "gibtsnicht")))


def test_cut_uses_configured_ffmpeg(configured, tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(split.subprocess, "run",
                        lambda cmd, **kw: commands.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    split.cut(tmp_path / "a.webm", 10.0, 20.0, tmp_path / "b.mp3", 192)
    assert commands[0][0] == str(configured / "ffmpeg")
    assert commands[0][commands[0].index("-b:a") + 1] == "192k"


def test_grab_frame_uses_configured_ffmpeg(configured, monkeypatch):
    commands = []
    monkeypatch.setattr(ocr.subprocess, "run",
                        lambda cmd, **kw: commands.append(cmd) or subprocess.CompletedProcess(cmd, 1, b"", b""))
    assert ocr.grab_frame("video.mp4", 5.0) is None
    assert commands[0][0] == str(configured / "ffmpeg")


def test_ytdlp_gets_ffmpeg_location(configured):
    assert ytdlp.base_opts()["ffmpeg_location"] == str(configured)
    ffmpeg.configure(None)
    assert "ffmpeg_location" not in ytdlp.base_opts()
