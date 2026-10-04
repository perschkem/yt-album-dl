import pytest

from ytdl.config import Config
from ytdl.library import Skipped, conflicts, final_path, place
from ytdl.metadata import MUSIK, Item


@pytest.fixture()
def cfg(tmp_path):
    return Config(musik_dir=tmp_path / "Musik", podcast_dir=tmp_path / "Pod", data_dir=tmp_path / "data",
                  bitrate=320, host="", port=0, ffmpeg_location=None)


def song(**kw):
    return Item(id="x", url="", mode=MUSIK, title="Titel", artist="Band", **kw)


def new_file(tmp_path, content):
    f = tmp_path / f"neu-{content}.mp3"
    f.write_text(content)
    return f


def existing(cfg, item):
    target = final_path(item, cfg)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("alt")
    return target


def test_keep_both(cfg, tmp_path):
    item = song()
    target = existing(cfg, item)
    result = place(new_file(tmp_path, "neu"), item, cfg)
    assert result.name == "Band - Titel (2).mp3" and target.read_text() == "alt"


def test_overwrite(cfg, tmp_path):
    item = song(on_conflict="overwrite")
    target = existing(cfg, item)
    assert place(new_file(tmp_path, "neu"), item, cfg) == target
    assert target.read_text() == "neu"
    assert [p.name for p in target.parent.iterdir()] == [target.name]  # keine Zwischendatei übrig


def test_skip(cfg, tmp_path):
    item = song(on_conflict="skip")
    target = existing(cfg, item)
    with pytest.raises(Skipped):
        place(new_file(tmp_path, "neu"), item, cfg)
    assert target.read_text() == "alt"


def test_format_per_item_changes_suffix_and_conflicts(cfg):
    mp3, m4a = song(), song(audio_format="m4a")
    existing(cfg, mp3)
    assert final_path(m4a, cfg).suffix == ".m4a"
    assert [c["id"] for c in conflicts([mp3], cfg)] == ["x"]
    assert conflicts([m4a], cfg) == []  # andere Endung → kein Konflikt
