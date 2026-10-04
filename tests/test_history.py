import json
import time

from ytdl.history import FAILED, FINISHED, History
from ytdl.metadata import MUSIK, PODCAST, Item


def song(n, **kw):
    return Item(id=f"v{n}", url=f"https://youtu.be/v{n}", mode=MUSIK, title=f"Titel {n}", artist="Band",
                album="Platte", **kw)


def test_record_and_query_newest_first(tmp_path):
    h = History(tmp_path)
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x" * 10)
    h.record(song(1), FINISHED, path=str(f), audio_format="mp3", bitrate=320)
    h.record(song(2, cover_url="https://x/c.jpg"), FAILED, error="HTTP Error 503", attempts=3, audio_format="m4a")
    data = h.query()
    assert data["total"] == 2
    first, second = data["entries"]
    assert first["tags"]["title"] == "Titel 2" and first["result"] == FAILED and first["attempts"] == 3
    assert first["cover"] == "eigene URL" and first["bitrate"] is None  # Bitrate nur bei MP3
    assert second["size"] == 10 and second["exists"] is True and second["tags"]["album"] == "Platte"


def test_filters_and_search(tmp_path):
    h = History(tmp_path)
    h.record(song(1), FINISHED)
    h.record(Item(id="p", url="https://youtu.be/p", mode=PODCAST, title="Folge 7", artist="Kanal"), FINISHED)
    h.record(song(3), FAILED, error="kaputt")
    assert h.query(mode=PODCAST)["total"] == 1
    assert h.query(result=FAILED)["total"] == 1
    assert h.query(q="folge kanal")["total"] == 1  # alle Wörter müssen vorkommen
    assert h.query(since=time.time() + 60)["total"] == 0
    assert h.query(limit=1, offset=1)["entries"][0]["tags"]["title"] == "Folge 7"


def test_album_cut_fields_and_missing_file(tmp_path):
    h = History(tmp_path)
    item = song(1, start=120.5, end=300.0, source_id="vid", boundary_source="Trackliste im Videobild (OCR)")
    h.record(item, FINISHED, path=str(tmp_path / "weg.mp3"))
    e = h.query()["entries"][0]
    assert (e["start"], e["end"], e["video_id"]) == (120.5, 300.0, "vid")
    assert e["boundary_source"].startswith("Trackliste") and e["exists"] is False


def test_broken_line_is_skipped_and_csv(tmp_path):
    h = History(tmp_path)
    h.record(song(1), FINISHED)
    with h.path.open("a") as fh:
        fh.write("{kaputt\n")
    h.record(song(2), FINISHED)
    assert h.query()["total"] == 2
    csv_text = h.to_csv()
    assert csv_text.splitlines()[0].startswith("Zeit;Ergebnis") and "Titel 2" in csv_text
    assert h.clear() == 2 and h.query()["total"] == 0


def test_job_manager_writes_history(client):
    from tests.test_web import item, wait_jobs
    from ytdl import web

    web.manager.history = History(client.cfg.data_dir)
    client.post("/api/jobs", json={"title": "x", "mode": "musik", "items": [item(1)]})
    wait_jobs(client, lambda j: j["done"] == 1)
    for _ in range(50):
        if web.manager.history.query()["total"]:
            break
        time.sleep(0.02)
    entries = web.manager.history.query()["entries"]
    assert entries and entries[0]["result"] == "fertig" and entries[0]["path"].endswith("v1.mp3")
    lines = [json.loads(l) for l in web.manager.history.path.read_text().splitlines()]
    assert lines[0]["url"] == "https://youtu.be/v1"
