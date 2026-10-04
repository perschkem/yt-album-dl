import time

from ytdl.activity import ActivityManager
from ytdl.status import Status

DONE, FAILED, NOTHING, SKIPPED = Status.DONE, Status.FAILED, Status.NOTHING, Status.SKIPPED


def wait(act, timeout=3.0):
    end = time.time() + timeout
    while act.status == "läuft" and time.time() < end:
        time.sleep(0.01)


def test_steps_and_result():
    def work(act):
        act.step("Eins").update("halb", 50)
        act.step("Zwei").nothing("leer")
        act.skip("Drei", "nicht nötig")
        act.step("Vier")
        return {"ok": True}

    act = ActivityManager().start("test", work)
    wait(act)
    data = act.to_dict()
    assert data["status"] == DONE and data["result"] == {"ok": True}
    assert [s["state"] for s in data["steps"]] == [DONE, NOTHING, SKIPPED, DONE]
    assert data["steps"][0]["detail"] == "halb"


def test_error_names_the_failing_step():
    def work(act):
        act.step("Audio laden").done()
        act.step("Lautstärkeverlauf berechnen")
        raise RuntimeError("ffmpeg konnte das Audio nicht lesen")

    act = ActivityManager().start("test", work)
    wait(act)
    assert act.status == FAILED
    assert act.error == "Fehler bei „Lautstärkeverlauf berechnen“: ffmpeg konnte das Audio nicht lesen"
    assert act.steps[-1].state == FAILED


def test_steps_report_elapsed_seconds(monkeypatch):
    from ytdl import activity as mod

    clock = {"now": 1000.0}
    monkeypatch.setattr(mod.time, "time", lambda: clock["now"])
    act = mod.Activity(id="x", kind="test")
    step = act.step("Video-Infos laden")
    clock["now"] += 4.6
    assert step.to_dict()["elapsed"] == 4 and step.to_dict()["progress"] is None  # unbestimmt
    step.done()
    clock["now"] += 10
    assert step.to_dict()["elapsed"] == 4  # nach dem Ende bleibt die Dauer stehen
