import threading
import time
from pathlib import Path

import pytest

from ytdl import jobs
from ytdl.config import Config
from ytdl.jobs import CUT, DOWNLOAD, JobManager, backoff_delay, is_permanent, is_throttled
from ytdl.metadata import MUSIK, Item


def make_cfg(tmp_path, **kw):
    base = dict(musik_dir=tmp_path, podcast_dir=tmp_path, data_dir=tmp_path, bitrate=320, host="", port=0,
                ffmpeg_location=None, parallel_downloads=3, parallel_cuts=2, max_retries=3)
    return Config(**{**base, **kw})


def item(n, **kw):
    return Item(id=f"v{n}", url="", mode=MUSIK, title=f"T{n}", artist="A", **kw)


def wait_until(predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    monkeypatch.setattr(jobs, "BACKOFF_BASE", 0.01)
    monkeypatch.setattr(jobs, "BACKOFF_MAX", 0.05)


def test_backoff_doubles_and_caps():
    no_jitter = lambda: 0.5  # noqa: E731  → Faktor 1.0
    assert [backoff_delay(a, no_jitter) for a in (1, 2, 3, 4)] == [0.01, 0.02, 0.04, 0.05]


def test_backoff_jitter_range(monkeypatch):
    monkeypatch.setattr(jobs, "BACKOFF_BASE", 2.0)
    monkeypatch.setattr(jobs, "BACKOFF_MAX", 120.0)
    assert backoff_delay(3, lambda: 0.0) == pytest.approx(6.4)
    assert backoff_delay(3, lambda: 1.0) == pytest.approx(9.6)
    assert backoff_delay(20, lambda: 0.5) == 120.0


def test_error_classification():
    assert is_permanent("ERROR: [youtube] abc: Private video. Sign in if you've been granted access")
    assert is_permanent("Video unavailable. This video has been removed by the uploader")
    assert not is_permanent("HTTP Error 503: Service Unavailable")
    assert is_throttled("HTTP Error 429: Too Many Requests")


def test_runs_downloads_in_parallel(tmp_path):
    running, peak, lock = 0, 0, threading.Lock()

    def runner(it, cfg, report):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.1)
        with lock:
            running -= 1
        report("fertig", 100.0)
        return tmp_path / f"{it.id}.mp3"

    mgr = JobManager(make_cfg(tmp_path), runners={DOWNLOAD: runner, CUT: runner})
    job = mgr.submit("x", MUSIK, [item(n) for n in range(6)])
    assert wait_until(lambda: mgr.snapshot()[0]["done"] == 6)
    assert peak == 3  # PARALLEL_DOWNLOADS
    assert all(t["status"] == "fertig" for t in mgr.snapshot()[0]["tasks"])
    assert job.folder() == str(tmp_path)


def test_cuts_use_their_own_limit(tmp_path):
    running, peak, lock = 0, 0, threading.Lock()

    def runner(it, cfg, report):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.1)
        with lock:
            running -= 1
        report("fertig", 100.0)
        return tmp_path / "x.mp3"

    mgr = JobManager(make_cfg(tmp_path), runners={DOWNLOAD: runner, CUT: runner})
    mgr.submit("album", MUSIK, [item(n, start=float(n), end=float(n + 1)) for n in range(5)])
    assert wait_until(lambda: mgr.snapshot()[0]["done"] == 5)
    assert peak == 2  # PARALLEL_CUTS


def test_transient_error_is_retried_with_backoff(tmp_path):
    calls = []

    def flaky(it, cfg, report):
        calls.append(time.time())
        if len(calls) < 3:
            raise RuntimeError("HTTP Error 503: Service Unavailable")
        report("fertig", 100.0)
        return tmp_path / "ok.mp3"

    mgr = JobManager(make_cfg(tmp_path), runners={DOWNLOAD: flaky, CUT: flaky})
    mgr.submit("x", MUSIK, [item(1)])
    assert wait_until(lambda: mgr.snapshot()[0]["tasks"][0]["status"] == "fertig")
    task = mgr.snapshot()[0]["tasks"][0]
    assert len(calls) == 3 and task["attempt"] == 3


def test_gives_up_after_max_attempts_then_manual_retry(tmp_path):
    fail = {"on": True}
    calls = []

    def runner(it, cfg, report):
        calls.append(1)
        if fail["on"]:
            raise RuntimeError("Verbindung abgebrochen")
        report("fertig", 100.0)
        return tmp_path / "ok.mp3"

    mgr = JobManager(make_cfg(tmp_path, max_retries=2), runners={DOWNLOAD: runner, CUT: runner})
    job = mgr.submit("x", MUSIK, [item(1)])
    assert wait_until(lambda: mgr.snapshot()[0]["tasks"][0]["status"] == "fehler")
    task = mgr.snapshot()[0]["tasks"][0]
    assert len(calls) == 3 and "nach 3 Versuchen" in task["error"]

    fail["on"] = False
    mgr.retry(job.id)
    assert wait_until(lambda: mgr.snapshot()[0]["tasks"][0]["status"] == "fertig")
    assert mgr.snapshot()[0]["tasks"][0]["attempt"] == 1


def test_permanent_error_is_not_retried(tmp_path):
    calls = []

    def runner(it, cfg, report):
        calls.append(1)
        raise RuntimeError("ERROR: [youtube] x: Private video")

    mgr = JobManager(make_cfg(tmp_path), runners={DOWNLOAD: runner, CUT: runner})
    mgr.submit("x", MUSIK, [item(1)])
    assert wait_until(lambda: mgr.snapshot()[0]["tasks"][0]["status"] == "fehler")
    time.sleep(0.1)
    assert len(calls) == 1


def test_waiting_task_does_not_block_others(tmp_path):
    order = []

    def runner(it, cfg, report):
        order.append(it.id)
        if it.id == "v0" and order.count("v0") == 1:
            raise RuntimeError("HTTP Error 503")
        report("fertig", 100.0)
        return tmp_path / f"{it.id}.mp3"

    mgr = JobManager(make_cfg(tmp_path, parallel_downloads=1), runners={DOWNLOAD: runner, CUT: runner})
    mgr.submit("x", MUSIK, [item(n) for n in range(3)])
    assert wait_until(lambda: mgr.snapshot()[0]["done"] == 3)
    assert order[:3] == ["v0", "v1", "v2"] and order[3] == "v0"  # v0 wartet, die anderen laufen weiter


def test_throttle_after_429(tmp_path, monkeypatch):
    mgr = JobManager(make_cfg(tmp_path), runners={DOWNLOAD: lambda *a: None, CUT: lambda *a: None})
    assert mgr._limit(DOWNLOAD, time.time()) == 3
    mgr._failed(jobs.Task(item=item(1), kind=DOWNLOAD), "HTTP Error 429: Too Many Requests")
    assert mgr._limit(DOWNLOAD, time.time()) == 1
    assert mgr._limit(CUT, time.time()) == 2
