"""API-Tests über den echten FastAPI-Client – Download/Schnitt durch Platzhalter ersetzt."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from ytdl import web
from ytdl.config import Config
from ytdl.jobs import CONVERT, CUT, FETCH, JobManager


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
        report("done", 100.0)
        return target

    monkeypatch.setattr(web, "cfg", cfg)
    runners = {FETCH: lambda it, cfg, report, workdir: tmp_path,
               CONVERT: lambda it, cfg, report, workdir: fake(it, cfg, report),
               CUT: lambda it, cfg, report, workdir: fake(it, cfg, report)}
    monkeypatch.setattr(web, "manager", JobManager(cfg, runners=runners))
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
    assert all(t["status"] == "done" and t["path"] for t in job["tasks"])


def test_retry_endpoint(client):
    client.calls["fail"].add("v1")
    job_id = client.post("/api/jobs", json={"title": "x", "mode": "musik", "items": [item(1)]}).json()["id"]
    wait_jobs(client, lambda j: j["failed"] == 1)
    client.calls["fail"].clear()
    res = client.post(f"/api/jobs/{job_id}/retry", json={"task_id": "v1"})
    assert res.status_code == 200
    wait_jobs(client, lambda j: j["tasks"][0]["status"] == "done")
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


def test_conflicts_endpoint_and_format(client):
    existing = client.cfg.musik_dir / "A" / "Singles" / "A - T1.mp3"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"x")
    body = {"mode": "musik", "items": [item(1), item(2)]}
    found = client.post("/api/conflicts", json=body).json()
    assert [c["id"] for c in found] == ["v1"] and found[0]["size"] == 1
    assert client.post("/api/conflicts", json={**body, "audio_format": "m4a"}).json() == []
    assert client.post("/api/conflicts", json={**body, "audio_format": "flac"}).status_code == 400


def test_skipped_items_are_not_submitted(client):
    res = client.post("/api/jobs", json={"mode": "musik", "items": [{**item(1), "on_conflict": "skip"}, item(2)]})
    assert res.json()["total"] == 1
    only_skip = client.post("/api/jobs", json={"mode": "musik", "items": [{**item(3), "on_conflict": "skip"}]})
    assert only_skip.status_code == 400


def test_clear_finished_jobs(client):
    client.post("/api/jobs", json={"title": "x", "mode": "musik", "items": [item(1)]})
    wait_jobs(client, lambda j: j["done"] == 1)
    assert client.delete("/api/jobs").json() == {"removed": 1}
    assert client.get("/api/jobs").json() == []


def test_event_stream_sends_changes_and_stops():
    """SSE-Generator direkt testen (der TestClient beendet unendliche Streams nicht sauber)."""
    import asyncio

    states = iter([{"n": 1}, {"n": 1}, {"n": 2}, {"n": 3, "done": True}])
    current = {"n": 0}

    def snapshot():
        current.update(next(states, current))
        return dict(current)

    class FakeRequest:
        async def is_disconnected(self):
            return False

    async def collect():
        return [m async for m in web._event_stream(FakeRequest(), snapshot, done=lambda d: d.get("done"),
                                                    interval=0)]

    messages = asyncio.run(collect())
    assert [json.loads(m[6:])["n"] for m in messages] == [1, 2, 3]  # unveränderter Zustand wird nicht erneut gesendet


def test_event_stream_stops_on_disconnect():
    import asyncio

    class Gone:
        async def is_disconnected(self):
            return True

    async def collect():
        return [m async for m in web._event_stream(Gone(), lambda: {"x": 1}, interval=0)]

    assert asyncio.run(collect()) == []


def test_job_events_route_exists(client):
    routes = {r.path for r in web.app.routes}
    assert {"/api/jobs/events", "/api/activities/{activity_id}/events"} <= routes


def test_settings_include_input_limits(client):
    data = client.get("/api/settings").json()
    assert data["limits"]["parallel_downloads"] == [1, 16] and 320 in data["bitrates"] and "firefox" in data["browsers"]


def test_cover_errors_become_400(client, monkeypatch):
    from ytdl.covers import CoverError

    def broken(url, size=300):
        raise CoverError("Unter der URL liegt kein Bild")

    monkeypatch.setattr(web, "thumbnail_preview", broken)
    monkeypatch.setattr(web, "check_cover", broken)
    for res in (client.get("/api/cover/thumbnail", params={"src": "https://x"}),
                client.post("/api/cover/check", json={"url": "https://x"})):
        assert res.status_code == 400 and res.json()["detail"] == "Unter der URL liegt kein Bild"


def test_unknown_activity_events(client):
    assert client.get("/api/activities/gibtsnicht/events").status_code == 404


def test_album_audio(client):
    assert client.get("/api/album/vid123/audio").status_code == 404
    folder = client.cfg.data_dir / "cache" / "vid123"
    folder.mkdir(parents=True)
    (folder / "audio.m4a").write_bytes(b"audio")
    (folder / "audio.jpg").write_bytes(b"bild")
    res = client.get("/api/album/vid123/audio")
    assert res.status_code == 200 and res.content == b"audio"


def test_album_endpoints_validate_id_and_start_activities(client, monkeypatch):
    started = []
    monkeypatch.setattr(web.activities, "start", lambda kind, func: started.append(kind) or type("A", (), {"id": "a1"}))
    for route, body in (("detect", {}), ("text", {"text": "x"}), ("scan", {})):
        assert client.post(f"/api/album/bad!id/{route}", json=body).status_code == 400
        assert client.post(f"/api/album/vid/{route}", json=body).json() == {"activity_id": "a1"}
    assert started == ["album-pausen", "album-trackliste", "album-scan"]


def test_album_job_without_analysis(client):
    res = client.post("/api/album/neu/jobs", json={"album": "A", "album_artist": "B", "tracks": [{"start": 0, "title": "x"}]})
    assert res.status_code == 400 and "nicht analysiert" in res.json()["detail"]


def analyzed(client, video_id="vid123", duration=300):
    folder = client.cfg.data_dir / "cache" / video_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "meta.json").write_text(json.dumps({"id": video_id, "url": f"https://youtu.be/{video_id}",
                                                  "duration": duration}))


def test_album_job_applies_decisions_by_id(client):
    analyzed(client)
    tracks = [{"start": 120, "artist": "A", "title": "Zwei"}, {"start": 0, "artist": "A", "title": "Eins"}]
    body = {"album": "Al", "album_artist": "A", "tracks": tracks}
    # IDs werden in Start-Reihenfolge vergeben – das Frontend muss sie nicht nachbauen
    res = client.post("/api/album/vid123/jobs", json={**body, "decisions": {"vid123-01": "skip"}})
    assert [t["label"] for t in res.json()["tasks"]] == ["A - Zwei"]
    only_skip = client.post("/api/album/vid123/jobs", json={**body, "decisions": {"vid123-01": "skip",
                                                                                  "vid123-02": "skip"}})
    assert only_skip.status_code == 400 and only_skip.json()["detail"] == "Alle Titel übersprungen"


def test_job_decisions_are_validated_and_applied(client):
    body = {"mode": "musik", "items": [item(1), item(2)]}
    bad = client.post("/api/jobs", json={**body, "decisions": {"v1": "löschen"}})
    assert bad.status_code == 400 and "löschen" in bad.json()["detail"]
    res = client.post("/api/jobs", json={**body, "decisions": {"v2": "skip", "v1": "overwrite"}})
    assert [t["id"] for t in res.json()["tasks"]] == ["v1"]
    assert web.manager.jobs[0].tasks[0].item.on_conflict == "overwrite"


def test_album_job_needs_ffmpeg(client, monkeypatch):
    analyzed(client)
    monkeypatch.setattr(web, "ffmpeg_available", lambda cfg: False)
    res = client.post("/api/album/vid123/jobs", json={"album": "Al", "album_artist": "A",
                                                      "tracks": [{"start": 0, "title": "Eins"}]})
    assert res.status_code == 400 and "ffmpeg" in res.json()["detail"]
