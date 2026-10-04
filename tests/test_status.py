import json

from ytdl.i18n import messages
from ytdl.status import FINISHED, LEGACY_RESULTS, Status


def test_codes_are_language_neutral_and_stable():
    """Die Codes stehen in data/history.jsonl, CSS-Klassen und Filtern – nie umbenennen."""
    assert {s.name: s.value for s in Status} == {
        "DONE": "done", "FAILED": "failed", "SKIPPED": "skipped", "WAITING": "waiting",
        "WAITING_FOR_CONVERT": "waiting_for_convert", "DOWNLOADING": "downloading", "CONVERTING": "converting",
        "CUTTING": "cutting", "TAGGING": "tagging", "RETRYING": "retrying", "PAUSED": "paused",
        "RUNNING": "running", "NOTHING": "nothing", "OVERWRITTEN": "overwritten",
    }


def test_every_status_has_a_label_in_every_language():
    for lang in ("de", "en"):
        assert all(f"status.{s}" in messages(lang) for s in Status), lang
    assert messages("de")["status.done"] == "fertig" and messages("en")["status.done"] == "done"


def test_behaves_like_plain_string():
    assert Status.DONE == "done" and f"{Status.FAILED}" == "failed"
    assert json.dumps({"status": Status.SKIPPED}) == '{"status": "skipped"}'


def test_finished_states():
    assert FINISHED == {"done", "failed", "skipped"}
    assert Status.PAUSED not in FINISHED and Status.OVERWRITTEN not in FINISHED


def test_legacy_results_map_old_history_entries():
    assert LEGACY_RESULTS == {"fertig": "done", "fehler": "failed", "übersprungen": "skipped",
                              "überschrieben": "overwritten"}
