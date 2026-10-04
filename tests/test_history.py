import json
import time

from ytdl.history import History
from ytdl.status import Status

FAILED, FINISHED = Status.FAILED, Status.DONE
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
    assert entries and entries[0]["result"] == "done" and entries[0]["path"].endswith("v1.mp3")
    lines = [json.loads(l) for l in web.manager.history.path.read_text().splitlines()]
    assert lines[0]["url"] == "https://youtu.be/v1"


def test_query_groups_by_job(tmp_path):
    h = History(tmp_path)
    files = []
    for n in (1, 2, 3):
        f = tmp_path / "Band" / "Platte" / f"{n:02d}.mp3"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
        files.append(f)
    # Album-Job mit drei Titeln (Reihenfolge der Fertigstellung durcheinander)
    for n in (2, 1, 3):
        h.record(song(n, track_no=n), FINISHED, path=str(files[n - 1]), job_id="job1", job_title="Platte")
    h.record(song(9), FAILED, error="kaputt", job_id="job2", job_title="Einzeltitel")
    h.record(song(8), FINISHED)  # alter Eintrag ohne Job-ID → eigene Gruppe

    data = h.query_groups()
    assert data["total"] == 3 and data["entries_total"] == 5
    newest, failed, album = data["groups"]
    assert newest["count"] == 1 and newest["title"] == "Platte"  # Titel aus Album-Tag
    assert failed["counts"] == {FAILED: 1} and failed["folder"] == ""
    assert album["title"] == "Platte" and album["count"] == 3
    assert [e["tags"]["track_no"] for e in album["entries"]] == [1, 2, 3]
    assert album["folder"] == str(tmp_path / "Band" / "Platte")
    assert h.query_groups(limit=1, offset=2)["groups"][0]["id"] == "job1"


def test_file_is_read_again_only_after_changes(tmp_path, monkeypatch):
    h = History(tmp_path)
    h.record(song(1), FINISHED)
    parsed = []
    original = History._parse
    monkeypatch.setattr(History, "_parse", staticmethod(lambda text: parsed.append(1) or original(text)))
    assert h.query()["total"] == 1 and h.query()["total"] == 1 and h.knows_path(tmp_path) is False
    assert len(parsed) == 1  # zwischengespeichert
    h.record(song(2), FINISHED)
    assert h.query()["total"] == 2 and len(parsed) == 2  # neue Zeile → neu eingelesen
    h.clear()
    assert h.query()["total"] == 0


def test_query_results_do_not_change_the_cache(tmp_path):
    h = History(tmp_path)
    h.record(song(1), FINISHED, path=str(tmp_path / "x.mp3"))
    first = h.query()["entries"][0]
    first["tags"]["title"] = "verändert"
    first["result"] = "kaputt"
    again = h.query()["entries"][0]
    assert again["result"] == FINISHED and again["tags"]["title"] == "Titel 1" and "exists" in again


def test_csv_columns_line_up(tmp_path):
    import csv
    import io

    h = History(tmp_path)
    h.record(song(1, track_no=4, year="2001", start=10.0, end=20.0), FAILED, error="kaputt", audio_format="mp3")
    rows = list(csv.reader(io.StringIO(h.to_csv()), delimiter=";"))
    header, row = rows
    record = dict(zip(header, row))
    assert len(header) == len(row) == 17
    assert (record["Ergebnis"], record["Interpret"], record["Titel"], record["Album"], record["Nr."]) == (
        "fehler", "Band", "Titel 1", "Platte", "4")
    assert (record["Jahr"], record["Start"], record["Ende"], record["Fehler"]) == ("2001", "10.0", "20.0", "kaputt")
    assert h.to_csv(result=FINISHED).count("\n") == 1  # Filter gelten auch für den Export


def test_group_counts_per_result(tmp_path):
    h = History(tmp_path)
    for n, result in ((1, FINISHED), (2, FAILED), (3, FINISHED)):
        h.record(song(n), result, job_id="j", job_title="Platte")
    (group,) = h.query_groups()["groups"]
    assert group["counts"] == {FINISHED: 2, FAILED: 1} and group["count"] == 3


def test_legacy_german_results_are_read_as_codes(tmp_path):
    """Ältere Einträge speicherten den deutschen Anzeigetext als Ergebnis."""
    h = History(tmp_path)
    h.path.write_text("\n".join(json.dumps({"ts": n, "result": r, "tags": {}}) for n, r in
                                enumerate(("fertig", "fehler", "übersprungen", "überschrieben"))) + "\n")
    assert [e["result"] for e in h.query()["entries"]] == ["overwritten", "skipped", "failed", "done"]
    assert h.query(result=FAILED)["total"] == 1
