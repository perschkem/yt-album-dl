import pytest

from ytdl import settings
from ytdl.settings import SETTINGS, InvalidSettings, validate


def test_every_request_field_has_a_setting():
    from ytdl.schemas import SettingsRequest

    assert set(SettingsRequest.model_fields) == set(SETTINGS)


def test_validate_returns_env_and_config_values(tmp_path):
    env, changes = validate({"musik_dir": f" {tmp_path / 'M'} ", "bitrate": 256, "max_retries": 0,
                             "cookies_from_browser": " Firefox ", "audio_format": "m4a"})
    assert env == {"MUSIK_DIR": str(tmp_path / "M"), "BITRATE": "256", "MAX_RETRIES": "0",
                   "COOKIES_FROM_BROWSER": "Firefox", "AUDIO_FORMAT": "m4a"}
    assert changes["musik_dir"] == tmp_path / "M" and changes["bitrate"] == 256 and changes["max_retries"] == 0
    assert (tmp_path / "M").is_dir()


def test_empty_folder_and_cookie_file_mean_not_set():
    env, changes = validate({"podcast_dir": "  ", "cookies_file": "", "cookies_from_browser": ""})
    assert env == {"PODCAST_DIR": "", "COOKIES_FILE": "", "COOKIES_FROM_BROWSER": ""}
    assert changes == {"podcast_dir": None, "cookies_file": None, "cookies_from_browser": ""}


def test_all_errors_are_collected(tmp_path):
    with pytest.raises(InvalidSettings) as err:
        validate({"bitrate": 999, "parallel_downloads": 17, "parallel_cuts": 0, "sleep_seconds": -1,
                  "audio_format": "flac", "cookies_file": str(tmp_path / "fehlt.txt"),
                  "cookies_from_browser": "firefox:/gibt/es/nicht", "max_retries": 3})
    assert err.value.fields == {
        "bitrate": "Erlaubt: 128, 160, 192, 256, 320", "parallel_downloads": "Erlaubt: 1–16",
        "parallel_cuts": "Erlaubt: 1–32", "sleep_seconds": "Erlaubt: 0–120", "audio_format": "mp3 oder m4a",
        "cookies_file": "Datei nicht gefunden", "cookies_from_browser": "Profilordner nicht gefunden"}


def test_current_and_limits(tmp_path, monkeypatch):
    from tests.test_jobs import make_cfg

    monkeypatch.setenv("MUSIK_DIR", r" D:\Musik ")
    current = settings.current(make_cfg(tmp_path, sleep_seconds=7))
    assert current["musik_dir"] == r"D:\Musik" and current["sleep_seconds"] == 7 and current["max_retries"] == 3
    assert settings.limits() == {"parallel_downloads": [1, 16], "parallel_cuts": [1, 32], "max_retries": [0, 10],
                                 "sleep_seconds": [0, 120]}


def test_messages_in_english(english, tmp_path):
    with pytest.raises(InvalidSettings) as err:
        validate({"bitrate": 1, "max_retries": 99, "audio_format": "ogg", "cookies_file": str(tmp_path / "x.txt")})
    assert str(err.value) == "Settings not saved"
    assert err.value.fields == {"bitrate": "Allowed: 128, 160, 192, 256, 320", "max_retries": "Allowed: 0–10",
                                "audio_format": "mp3 or m4a", "cookies_file": "File not found"}
