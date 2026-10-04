import time
from pathlib import Path

import pytest

from tests.test_jobs import as_download, item, make_cfg, wait_until
from ytdl import downloader, jobs
from ytdl.jobs import JobManager
from ytdl.metadata import MUSIK

BOT = "ERROR: [youtube] cb5Q6Y6dGKg: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies"


def test_bot_check_detection_and_hint():
    assert downloader.is_bot_check(BOT)
    assert not downloader.is_bot_check("Sign in to confirm your age")
    assert "Einstellungen" in downloader.friendly_error(BOT)
    assert downloader.friendly_error("HTTP Error 503") == "HTTP Error 503"


def test_bot_check_pauses_all_downloads_without_using_attempts(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "BOT_PAUSE_SECONDS", 60)
    calls = []

    def runner(it, cfg, report):
        calls.append(it.id)
        if it.id == "v0" and calls.count("v0") == 1:
            raise RuntimeError(BOT)
        report("fertig", 100.0)

    mgr = JobManager(make_cfg(tmp_path, parallel_downloads=1), runners=as_download(runner, tmp_path))
    mgr.submit("x", MUSIK, [item(n) for n in range(3)])
    assert wait_until(lambda: mgr.snapshot()[0]["tasks"][0]["status"] == "pausiert")
    time.sleep(0.2)
    assert calls == ["v0"]  # die anderen Titel warten mit, statt YouTube weiter anzufragen
    task = mgr.snapshot()[0]["tasks"][0]
    assert task["attempt"] == 1 and task["retry_in"] > 50 and "Bot-Prüfung" in task["detail"]

    assert mgr.resume() == 1
    assert wait_until(lambda: mgr.snapshot()[0]["done"] == 3)
    assert sorted(calls) == ["v0", "v0", "v1", "v2"]


def test_repeated_bot_check_finally_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "BOT_PAUSE_SECONDS", 0.01)

    def runner(it, cfg, report):
        raise RuntimeError(BOT)

    mgr = JobManager(make_cfg(tmp_path), runners=as_download(runner, tmp_path))
    mgr.submit("x", MUSIK, [item(1)])
    assert wait_until(lambda: mgr.snapshot()[0]["tasks"][0]["status"] == "fehler")
    assert "Einstellungen" in mgr.snapshot()[0]["tasks"][0]["error"]


def test_cookie_file_gets_private_copy_per_run(tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n")
    cfg = make_cfg(tmp_path)
    cfg.cookies_file = cookies
    downloader.configure_auth(cfg)
    try:
        a, b = downloader._base_opts()["cookiefile"], downloader._base_opts()["cookiefile"]
        assert a != b and Path(a).read_text() == cookies.read_text()
        assert str(cookies) not in (a, b)  # Original wird nie an yt-dlp gegeben (würde überschrieben)
    finally:
        downloader.configure_auth(make_cfg(tmp_path))


def test_browser_spec():
    assert downloader.parse_browser_spec("Firefox") == ("firefox", None, None, None)
    with pytest.raises(ValueError):
        downloader.parse_browser_spec("netscape")


def test_settings_validate_cookie_file(settings_client, tmp_path):
    bad = tmp_path / "keine-cookies.txt"
    bad.write_text("hallo welt")
    res = settings_client.put("/api/settings", json={"cookies_file": str(bad), "cookies_from_browser": "netscape",
                                                      "sleep_seconds": 500})
    assert set(res.json()["detail"]["fields"]) == {"cookies_file", "cookies_from_browser", "sleep_seconds"}
    good = tmp_path / "cookies.txt"
    good.write_text("# Netscape HTTP Cookie File\n")
    res = settings_client.put("/api/settings", json={"cookies_file": str(good), "sleep_seconds": 5})
    assert res.status_code == 200 and res.json()["sleep_seconds"] == 5
    from ytdl import web
    assert web.cfg.cookies_file == good
