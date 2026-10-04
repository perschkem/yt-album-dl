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


@pytest.fixture()
def cookie_cfg(tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc\n")
    cfg = make_cfg(tmp_path)
    cfg.cookies_file = cookies
    downloader.configure_auth(cfg)
    downloader._auth.update(active_until=0.0, last_bot_check=0.0)
    yield cookies
    downloader.configure_auth(make_cfg(tmp_path))
    downloader._auth.update(active_until=0.0, last_bot_check=0.0)


def test_cookies_only_after_bot_check(cookie_cfg):
    assert "cookiefile" not in downloader._base_opts()  # normal: ohne Anmeldung
    downloader._auth["active_until"] = time.time() + 60
    a, b = downloader._base_opts()["cookiefile"], downloader._base_opts()["cookiefile"]
    assert a != b and Path(a).read_text() == cookie_cfg.read_text()
    assert str(cookie_cfg) not in (a, b)  # Original wird nie an yt-dlp gegeben (würde überschrieben)


def test_fallback_retries_once_with_cookies(cookie_cfg):
    seen = []

    def call():
        opts = downloader._base_opts()
        seen.append("cookiefile" in opts)
        if not opts.get("cookiefile"):
            raise RuntimeError(BOT)
        return "ok"

    assert downloader.with_cookie_fallback(call) == "ok"
    assert seen == [False, True]
    status = downloader.auth_status()
    assert status["cookies_active"] and status["recent_bot_check"] and status["cookies_until"] > time.time() + 3000
    seen.clear()
    assert downloader.with_cookie_fallback(call) == "ok" and seen == [True]  # bleibt eine Weile mit Anmeldung


def test_fallback_without_cookies_raises_and_notes_bot_check(tmp_path):
    downloader.configure_auth(make_cfg(tmp_path))
    downloader._auth.update(active_until=0.0, last_bot_check=0.0)

    def call():
        raise RuntimeError(BOT)

    with pytest.raises(RuntimeError, match="not a bot"):
        downloader.with_cookie_fallback(call)
    assert downloader.auth_status()["recent_bot_check"] and not downloader.auth_status()["cookies_active"]
    downloader._auth["last_bot_check"] = 0.0


def test_other_errors_do_not_trigger_cookies(cookie_cfg):
    def call():
        raise RuntimeError("HTTP Error 503")

    with pytest.raises(RuntimeError, match="503"):
        downloader.with_cookie_fallback(call)
    assert not downloader.cookies_active()


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
