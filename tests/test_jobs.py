import threading
import time

import pytest

from ytdl import jobs
from ytdl.config import Config
from ytdl.jobs import CONVERT, CPU, CUT, FETCH, NET, JobManager, backoff_delay, is_permanent, is_throttled
from ytdl.library import Skipped
from ytdl.metadata import MUSIK, Item


def make_cfg(tmp_path, **kw):
    base = {"musik_dir": tmp_path, "podcast_dir": tmp_path, "data_dir": tmp_path, "bitrate": 320, "host": "", "port": 0,
            "ffmpeg_location": None, "parallel_downloads": 3, "parallel_cuts": 2, "max_retries": 3}
    return Config(**{**base, **kw})


def as_download(fn, tmp_path):
    """Läuft `fn` in der Download-Stufe (bzw. beim Schneiden); Konvertieren ist ein schneller Platzhalter."""
    def fetch(it, cfg, report, workdir):
        fn(it, cfg, report)
        return tmp_path

    def convert(it, cfg, report, workdir):
        report("done", 100.0)
        return tmp_path / f"{it.id}.mp3"

    return {FETCH: fetch, CONVERT: convert, CUT: lambda it, cfg, report, workdir: fn(it, cfg, report)}


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
    no_jitter = lambda: 0.5  # → Faktor 1.0
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
        report("done", 100.0)
        return tmp_path / f"{it.id}.mp3"

    mgr = JobManager(make_cfg(tmp_path), runners=as_download(runner, tmp_path))
    job = mgr.submit("x", MUSIK, [item(n) for n in range(6)])
    assert wait_until(lambda: mgr.snapshot()[0]["done"] == 6)
    assert peak == 3  # PARALLEL_DOWNLOADS
    assert all(t["status"] == "done" for t in mgr.snapshot()[0]["tasks"])
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
        report("done", 100.0)
        return tmp_path / "x.mp3"

    mgr = JobManager(make_cfg(tmp_path), runners=as_download(runner, tmp_path))
    mgr.submit("album", MUSIK, [item(n, start=float(n), end=float(n + 1)) for n in range(5)])
    assert wait_until(lambda: mgr.snapshot()[0]["done"] == 5)
    assert peak == 2  # PARALLEL_CUTS


def test_transient_error_is_retried_with_backoff(tmp_path):
    calls = []

    def flaky(it, cfg, report):
        calls.append(time.time())
        if len(calls) < 3:
            raise RuntimeError("HTTP Error 503: Service Unavailable")
        report("done", 100.0)
        return tmp_path / "ok.mp3"

    mgr = JobManager(make_cfg(tmp_path), runners=as_download(flaky, tmp_path))
    mgr.submit("x", MUSIK, [item(1)])
    assert wait_until(lambda: mgr.snapshot()[0]["tasks"][0]["status"] == "done")
    assert len(calls) == 3


def test_gives_up_after_max_attempts_then_manual_retry(tmp_path):
    fail = {"on": True}
    calls = []

    def runner(it, cfg, report):
        calls.append(1)
        if fail["on"]:
            raise RuntimeError("Verbindung abgebrochen")
        report("done", 100.0)
        return tmp_path / "ok.mp3"

    mgr = JobManager(make_cfg(tmp_path, max_retries=2), runners=as_download(runner, tmp_path))
    job = mgr.submit("x", MUSIK, [item(1)])
    assert wait_until(lambda: mgr.snapshot()[0]["tasks"][0]["status"] == "failed")
    task = mgr.snapshot()[0]["tasks"][0]
    assert len(calls) == 3 and "nach 3 Versuchen" in task["error"]

    fail["on"] = False
    mgr.retry(job.id)
    assert wait_until(lambda: mgr.snapshot()[0]["tasks"][0]["status"] == "done")


def test_permanent_error_is_not_retried(tmp_path):
    calls = []

    def runner(it, cfg, report):
        calls.append(1)
        raise RuntimeError("ERROR: [youtube] x: Private video")

    mgr = JobManager(make_cfg(tmp_path), runners=as_download(runner, tmp_path))
    mgr.submit("x", MUSIK, [item(1)])
    assert wait_until(lambda: mgr.snapshot()[0]["tasks"][0]["status"] == "failed")
    time.sleep(0.1)
    assert len(calls) == 1


def test_waiting_task_does_not_block_others(tmp_path):
    order = []

    def runner(it, cfg, report):
        order.append(it.id)
        if it.id == "v0" and order.count("v0") == 1:
            raise RuntimeError("HTTP Error 503")
        report("done", 100.0)
        return tmp_path / f"{it.id}.mp3"

    mgr = JobManager(make_cfg(tmp_path, parallel_downloads=1), runners=as_download(runner, tmp_path))
    mgr.submit("x", MUSIK, [item(n) for n in range(3)])
    assert wait_until(lambda: mgr.snapshot()[0]["done"] == 3)
    assert order[:3] == ["v0", "v1", "v2"] and order[3] == "v0"  # v0 wartet, die anderen laufen weiter


def test_throttle_after_429(tmp_path, monkeypatch):
    mgr = JobManager(make_cfg(tmp_path), runners=as_download(lambda *a: None, tmp_path))
    assert mgr._limit(NET, time.time()) == 3
    mgr._failed(jobs.Task(item=item(1), stage=FETCH), "HTTP Error 429: Too Many Requests")
    assert mgr._limit(NET, time.time()) == 1
    assert mgr._limit(CPU, time.time()) == 2


def test_pipeline_downloads_continue_while_converting(tmp_path):
    """Netzwerk-Worker warten nicht auf ffmpeg: während langsam konvertiert wird, laufen alle Downloads durch."""
    fetched, converting, peak_cpu, lock = [], 0, 0, threading.Lock()

    def fetch(it, cfg, report, workdir):
        fetched.append(it.id)
        return tmp_path

    def convert(it, cfg, report, folder):
        nonlocal converting, peak_cpu
        with lock:
            converting += 1
            peak_cpu = max(peak_cpu, converting)
        time.sleep(0.15)
        with lock:
            converting -= 1
        report("done", 100.0)
        return tmp_path / f"{it.id}.mp3"

    mgr = JobManager(make_cfg(tmp_path, parallel_downloads=1, parallel_cuts=2),
                     runners={FETCH: fetch, CONVERT: convert, CUT: convert})
    mgr.submit("x", MUSIK, [item(n) for n in range(5)])
    assert wait_until(lambda: len(fetched) == 5, timeout=0.3)  # lange bevor alle konvertiert sind
    assert wait_until(lambda: mgr.snapshot()[0]["done"] == 5)
    assert peak_cpu == 2


def test_skipped_counts_as_done(tmp_path):
    def convert(it, cfg, report, folder):
        raise Skipped("übersprungen – existiert bereits: x.mp3")

    mgr = JobManager(make_cfg(tmp_path), runners={FETCH: lambda *a: tmp_path, CONVERT: convert, CUT: convert})
    mgr.submit("x", MUSIK, [item(1)])
    job = None
    assert wait_until(lambda: mgr.snapshot()[0]["done"] == 1)
    job = mgr.snapshot()[0]
    assert job["skipped"] == 1 and job["failed"] == 0 and job["tasks"][0]["status"] == "skipped"


def test_clear_finished_keeps_running_jobs(tmp_path):
    gate = threading.Event()

    def slow(it, cfg, report):
        gate.wait(2)
        return tmp_path

    mgr = JobManager(make_cfg(tmp_path), runners=as_download(slow, tmp_path))
    gate.set()
    mgr.submit("done", MUSIK, [item(1)])
    assert wait_until(lambda: mgr.snapshot()[0]["done"] == 1)
    gate.clear()
    mgr.submit("running", MUSIK, [item(2)])
    assert mgr.clear_finished() == 1
    assert [j["title"] for j in mgr.snapshot()] == ["running"]
    gate.set()


def test_overall_progress_is_one_continuous_bar():
    from ytdl.jobs import overall_progress

    assert [overall_progress(FETCH, p) for p in (0, 50, 100)] == [0.0, 35.0, 70.0]
    assert [overall_progress(CONVERT, p) for p in (0, 80, 100)] == [70.0, 94.0, 100.0]
    assert overall_progress(CUT, 50) == 50.0


def test_progress_never_jumps_back_between_stages(tmp_path):
    seen = []

    def fetch(it, cfg, report, workdir):
        for pct in (0, 50, 100):
            report("downloading", pct)
            seen.append(mgr.snapshot()[0]["tasks"][0]["progress"])
        return tmp_path

    def convert(it, cfg, report, folder):
        for status, pct in (("converting", 0), ("tagging", 80), ("done", 100)):
            report(status, pct)
            seen.append(mgr.snapshot()[0]["tasks"][0]["progress"])
        return tmp_path / "x.mp3"

    mgr = JobManager(make_cfg(tmp_path), runners={FETCH: fetch, CONVERT: convert, CUT: convert})
    mgr.submit("x", MUSIK, [item(1)])
    assert wait_until(lambda: mgr.snapshot()[0]["done"] == 1)
    assert seen == sorted(seen) and seen[-1] == 100.0


def test_history_errors_are_logged_not_raised(tmp_path, caplog):
    class BrokenHistory:
        def record(self, *a, **kw):
            raise OSError("Platte voll")

    def runner(it, cfg, report):
        report("done", 100.0)

    mgr = JobManager(make_cfg(tmp_path), runners=as_download(runner, tmp_path), history=BrokenHistory())
    with caplog.at_level("ERROR", logger="ytdl.jobs"):
        mgr.submit("x", MUSIK, [item(1)])
        assert wait_until(lambda: mgr.snapshot()[0]["done"] == 1)
        assert wait_until(lambda: "Historie" in caplog.text)
    assert mgr.snapshot()[0]["tasks"][0]["status"] == "done"  # Download bleibt erfolgreich


# ---------- Task: Zustandsübergänge ----------

def test_task_report_maps_stage_progress():
    task = jobs.Task(item=item(1), stage=CONVERT)
    task.report("tagging", 50.0, "Cover")
    assert (task.status, task.progress, task.detail) == ("tagging", 85.0, "Cover")


def test_task_advance_and_restart_stage(tmp_path):
    task = jobs.Task(item=item(1), stage=FETCH, attempt=3)
    task.advance(str(tmp_path))
    assert (task.stage, task.attempt, task.status, task.progress) == (CONVERT, 1, "waiting_for_convert", 70.0)
    task.restart_stage()
    assert task.stage == CONVERT  # Download noch da → nur neu konvertieren
    task.workdir = str(tmp_path / "weg")
    task.restart_stage()
    assert task.stage == FETCH  # Download weg → von vorn


def test_task_reset_for_retry(tmp_path):
    task = jobs.Task(item=item(1), stage=CONVERT, workdir=str(tmp_path / "weg"), attempt=4, next_try=99.0)
    task.fail("kaputt")
    assert (task.status, task.error) == ("failed", "kaputt")
    task.reset_for_retry()
    assert (task.status, task.error, task.attempt, task.next_try, task.stage, task.progress) == (
        "waiting", "", 1, 0.0, FETCH, 0.0)


def test_task_skip_and_finish():
    task = jobs.Task(item=item(1), stage=CUT, detail="cutting")
    task.finish("/m/x.mp3")
    assert (task.path, task.detail) == ("/m/x.mp3", "")
    task.skip("übersprungen – existiert bereits")
    assert (task.status, task.progress) == ("skipped", 100.0)


def test_failed_convert_retries_without_new_download(tmp_path):
    """Scheitert nur das Konvertieren, wird nicht erneut geladen (Arbeitsverzeichnis bleibt)."""
    calls = []

    def fetch(it, cfg, report, workdir):
        calls.append("fetch")
        return tmp_path

    def convert(it, cfg, report, workdir):
        calls.append("convert")
        assert workdir == tmp_path
        if calls.count("convert") == 1:
            raise RuntimeError("ffmpeg: kurz kaputt")
        report("done", 100.0)
        return tmp_path / "x.mp3"

    mgr = JobManager(make_cfg(tmp_path), runners={FETCH: fetch, CONVERT: convert, CUT: convert})
    mgr.submit("x", MUSIK, [item(1)])
    assert wait_until(lambda: mgr.snapshot()[0]["done"] == 1)
    assert calls == ["fetch", "convert", "convert"]


def test_real_runners_share_one_signature():
    import inspect

    from ytdl.albumvideo import cut_track
    from ytdl.downloader import convert, fetch

    for runner in (fetch, convert, cut_track):
        assert list(inspect.signature(runner).parameters)[:4] == ["item", "cfg", "progress", "workdir"], runner


def test_permanent_error_does_not_depend_on_the_message_language(tmp_path, english):
    from ytdl.errors import PermanentError

    calls = []

    def runner(it, cfg, report):
        calls.append(1)
        raise PermanentError("The cached audio is missing – please analyze the video again")

    mgr = JobManager(make_cfg(tmp_path), runners=as_download(runner, tmp_path))
    mgr.submit("x", MUSIK, [item(1, start=0.0, end=1.0)])
    assert wait_until(lambda: mgr.snapshot()[0]["tasks"][0]["status"] == "failed")
    time.sleep(0.1)
    assert len(calls) == 1


def test_retry_details_in_english(tmp_path, english):
    def runner(it, cfg, report):
        raise RuntimeError("HTTP Error 503")

    mgr = JobManager(make_cfg(tmp_path, max_retries=1), runners=as_download(runner, tmp_path))
    mgr._failed(jobs.Task(item=item(1), stage=FETCH), "HTTP Error 503")
    task = mgr._pending[-1]
    assert task.detail == "Attempt 2/2 – last error: HTTP Error 503"
    mgr.submit("x", MUSIK, [item(2)])
    assert wait_until(lambda: mgr.snapshot()[0]["tasks"][0]["status"] == "failed")
    assert mgr.snapshot()[0]["tasks"][0]["error"] == "HTTP Error 503 (after 2 attempts)"
