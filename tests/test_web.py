"""API-Tests über den echten FastAPI-Client – Download/Schnitt durch Platzhalter ersetzt."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from ytdl import web
from ytdl.config import Config
from ytdl.jobs import CUT, DOWNLOAD, JobManager


@pytest.fixture()
def client(tmp_path, monkeypatch):
    cfg = Config(musik_dir=tmp_path / "Musik", podcast_dir=tmp_path / "Podcasts", data_dir=tmp_path / "data",
                 bitrate=320, host="", port=0, ffmpeg_location=None, parallel_downloads=2, parallel_cuts=2,
                 max_retries=1)
    calls = {"fail": set()}

    def fake(item, cfg, report):
        if item.id in calls["fail"]:
            raise RuntimeError("HTTP Error 503")
        target = cfg.musik_dir / f"{item.id}.mp3"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        report("fertig", 100.0)
        return target

    monkeypatch.setattr(web, "cfg", cfg)
    monkeypatch.setattr(web, "manager", JobManager(cfg, runners={DOWNLOAD: fake, CUT: fake}))
    monkeypatch.setattr(web, "ffmpeg_available", lambda cfg: True)
    monkeypatch.setattr("ytdl.jobs.BACKOFF_BASE", 0.01)
    c = TestClient(web.app)
    c.calls = calls
    c.cfg = cfg
    return c


def wait_jobs(client, predicate, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        jobs = client.get("/api/jobs").json()
        if jobs and predicate(jobs[0]):
            return jobs[0]
        time.sleep(0.02)
    raise AssertionError(client.get("/api/jobs").json())


def item(n):
    return {"id": f"v{n}", "url": f"https://youtu.be/v{n}", "title": f"T{n}", "artist": "A"}


def test_config(client):
    data = client.get("/api/config").json()
    assert data["audio_format"] == "mp3" and data["parallel_downloads"] == 2


def test_submit_and_list_jobs(client):
    res = client.post("/api/jobs", json={"title": "x", "mode": "musik", "items": [item(1), item(2)]})
    assert res.status_code == 200 and res.json()["total"] == 2 and res.json()["tasks"][0]["max_attempts"] == 2
    job = wait_jobs(client, lambda j: j["done"] == 2)
    assert job["failed"] == 0 and job["folder"] == str(client.cfg.musik_dir)
    assert all(t["status"] == "fertig" and t["path"] for t in job["tasks"])


def test_retry_endpoint(client):
    client.calls["fail"].add("v1")
    job_id = client.post("/api/jobs", json={"title": "x", "mode": "musik", "items": [item(1)]}).json()["id"]
    wait_jobs(client, lambda j: j["failed"] == 1)
    client.calls["fail"].clear()
    res = client.post(f"/api/jobs/{job_id}/retry", json={"task_id": "v1"})
    assert res.status_code == 200
    wait_jobs(client, lambda j: j["tasks"][0]["status"] == "fertig")
    assert client.post("/api/jobs/gibtsnicht/retry", json={}).status_code == 404


def test_album_job_endpoint(client):
    folder = client.cfg.data_dir / "cache" / "vid123"
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"id": "vid123", "url": "https://youtu.be/vid123", "duration": 300}))
    tracks = [{"start": 0, "artist": "A", "title": "Eins"}, {"start": 120, "artist": "A", "title": "Zwei"}]
    res = client.post("/api/album/vid123/jobs", json={"album": "Al", "album_artist": "A", "tracks": tracks})
    assert res.status_code == 200 and res.json()["total"] == 2
    wait_jobs(client, lambda j: j["done"] == 2)


def test_open_rejects_paths_outside_target_dirs(client):
    assert client.post("/api/open", json={"path": "/etc/passwd"}).status_code == 403


def test_unknown_activity(client):
    assert client.get("/api/activities/gibtsnicht").status_code == 404


def test_invalid_album_id(client):
    assert client.post("/api/album/bad!id/detect", json={}).status_code == 400
    # Pfad-Tricks erreichen die Route gar nicht
    assert client.post("/api/album/..%2Fetc/detect", json={}).status_code >= 400
