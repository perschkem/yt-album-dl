import os

import pytest
from dotenv import dotenv_values

from ytdl import web
from ytdl.config import Config, MissingFolder, update_env_file
from ytdl.metadata import MUSIK, PODCAST


def test_update_env_keeps_comments_and_other_lines(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# Kommentar\nMUSIK_DIR=/alt\nPORT=8000\n")
    monkeypatch.setattr(os, "environ", dict(os.environ))
    update_env_file({"MUSIK_DIR": r"D:\Meine Musik", "PODCAST_DIR": r"D:\Podcasts"}, env)
    text = env.read_text()
    assert text.startswith("# Kommentar\n") and "PORT=8000" in text
    values = dotenv_values(env)
    assert values["MUSIK_DIR"] == r"D:\Meine Musik"  # Leerzeichen + Backslashes überstehen das Einlesen
    assert values["PODCAST_DIR"] == r"D:\Podcasts"


def test_env_value_with_single_quote(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    monkeypatch.setattr(os, "environ", dict(os.environ))
    update_env_file({"MUSIK_DIR": r"D:\Rock 'n' Roll"}, env)
    assert dotenv_values(env)["MUSIK_DIR"] == r"D:\Rock 'n' Roll"


def test_missing_folder_has_clear_message(tmp_path):
    cfg = Config(musik_dir=None, podcast_dir=tmp_path, data_dir=tmp_path, bitrate=320, host="", port=0,
                 ffmpeg_location=None)
    assert cfg.root(PODCAST) == tmp_path
    with pytest.raises(MissingFolder, match="Musik.*Einstellungen"):
        cfg.root(MUSIK)


@pytest.fixture()
def settings_client(client, tmp_path, monkeypatch):
    env = tmp_path / ".env"
    monkeypatch.setattr("ytdl.config.ENV_FILE", env)
    monkeypatch.setattr(web, "update_env_file", lambda values: __import__("ytdl.config").config.update_env_file(values, env))
    monkeypatch.setattr(os, "environ", dict(os.environ))
    client.env = env
    return client


def test_settings_roundtrip(settings_client, tmp_path):
    target = tmp_path / "neu" / "Musik"
    res = settings_client.put("/api/settings", json={"musik_dir": str(target), "bitrate": 256, "audio_format": "m4a"})
    assert res.status_code == 200, res.json()
    assert target.is_dir()  # wird angelegt
    assert web.cfg.musik_dir == target and web.cfg.bitrate == 256 and web.cfg.audio_format == "m4a"
    values = dotenv_values(settings_client.env)
    assert values["MUSIK_DIR"] == str(target) and values["BITRATE"] == "256"
    assert settings_client.get("/api/settings").json()["musik_dir"] == str(target)


def test_settings_validation(settings_client):
    res = settings_client.put("/api/settings", json={"bitrate": 999, "parallel_downloads": 0,
                                                      "musik_dir": "/proc/kein/ordner"})
    assert res.status_code == 400
    fields = res.json()["detail"]["fields"]
    assert set(fields) == {"bitrate", "parallel_downloads", "musik_dir"}
    assert not settings_client.env.exists()  # bei Fehlern wird nichts geschrieben


def test_submit_without_folder_is_rejected(settings_client, monkeypatch):
    monkeypatch.setattr(web.cfg, "musik_dir", None)
    res = settings_client.post("/api/jobs", json={"mode": "musik", "items": [{"id": "v1", "url": "", "title": "T", "artist": "A"}]})
    assert res.status_code == 400 and res.json()["missing_folder"] is True


def test_running_job_keeps_its_folder(settings_client, tmp_path):
    job = settings_client.post("/api/jobs", json={"mode": "musik", "items": [{"id": "v1", "url": "", "title": "T", "artist": "A"}]})
    old_root = web.cfg.musik_dir
    settings_client.put("/api/settings", json={"musik_dir": str(tmp_path / "anderer")})
    task = next(t for j in web.manager.jobs for t in j.tasks)
    assert task.item.target_root == str(old_root)


def test_audio_format_from_env_is_validated():
    from ytdl.config import AUDIO_FORMATS, _audio_format

    assert AUDIO_FORMATS == ("mp3", "m4a")
    assert _audio_format(" M4A ") == "m4a"
    with pytest.raises(ValueError, match="flac"):
        _audio_format("flac")
