import json

from ytdl.status import FINISHED, Status


def test_values_stay_stable():
    """Die Texte stehen in der Oberfläche, in CSS-Klassen und in data/history.jsonl – nie umbenennen."""
    assert {s.name: s.value for s in Status} == {
        "DONE": "fertig", "FAILED": "fehler", "SKIPPED": "übersprungen", "WAITING": "wartet",
        "WAITING_FOR_CONVERT": "wartet auf Konvertierung", "DOWNLOADING": "lädt", "CONVERTING": "konvertiert",
        "CUTTING": "schneidet", "TAGGING": "taggt", "RETRYING": "neuer Versuch", "PAUSED": "pausiert",
        "RUNNING": "läuft", "NOTHING": "nichts gefunden", "OVERWRITTEN": "überschrieben",
    }


def test_behaves_like_plain_string():
    assert Status.DONE == "fertig" and f"{Status.FAILED}" == "fehler"
    assert json.dumps({"status": Status.SKIPPED}, ensure_ascii=False) == '{"status": "übersprungen"}'


def test_finished_states():
    assert FINISHED == {"fertig", "fehler", "übersprungen"}
    assert Status.PAUSED not in FINISHED and Status.OVERWRITTEN not in FINISHED
