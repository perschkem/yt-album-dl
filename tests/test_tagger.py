import shutil
import subprocess

import pytest
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from PIL import Image

from ytdl.metadata import MUSIK, PODCAST, Item
from ytdl.tagger import VARIOUS_ARTISTS, tag_values, write_tags


def album_song(**kw):
    fields = {"id": "1", "url": "https://youtu.be/1", "mode": MUSIK, "title": "Song", "artist": "B feat. C",
              "album": "Platte", "album_artist": "B", "track_no": 3, "track_total": 12, "year": "2001", "genre": "Rock"}
    return Item(**{**fields, **kw})


def test_tag_values_music():
    values = tag_values(album_song())
    assert values == {"title": "Song", "artist": "B feat. C", "album_artist": "B", "album": "Platte",
                      "compilation": False, "track": (3, 12), "date": "2001", "genre": "Rock",
                      "comment": "https://youtu.be/1", "url": "https://youtu.be/1"}


def test_tag_values_single_and_sampler():
    single = tag_values(Item(id="1", url="", mode=MUSIK, title="S", artist="A"))
    assert single["album"] is None and single["track"] is None and single["album_artist"] == "A"
    assert single["url"] is None and single["comment"] is None
    assert tag_values(album_song(album_artist=VARIOUS_ARTISTS))["compilation"] is True


def test_tag_values_podcast_uses_date_and_description():
    episode = Item(id="p", url="https://youtu.be/p", mode=PODCAST, title="Folge", artist="Kanal", year="2026",
                   date="2026-01-02", description="Shownotes")
    values = tag_values(episode)
    assert values["date"] == "2026-01-02" and values["comment"] == "Shownotes"


@pytest.fixture()
def silent(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg fehlt")

    def make(suffix):
        path = tmp_path / f"x.{suffix}"
        codec = ["-c:a", "aac"] if suffix == "m4a" else []
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc", "-t", "0.2", *codec, str(path)],
                       check=True)
        return path
    return make


def test_mp3_and_m4a_get_the_same_tags(silent, tmp_path):
    cover = tmp_path / "c.png"
    Image.new("RGB", (64, 64), "red").save(cover)
    item = album_song()
    mp3, m4a = silent("mp3"), silent("m4a")
    write_tags(mp3, item, cover)
    write_tags(m4a, item, cover)

    id3 = ID3(mp3)
    assert [str(id3[k]) for k in ("TIT2", "TPE1", "TPE2", "TALB", "TRCK", "TDRC", "TCON")] == [
        "Song", "B feat. C", "B", "Platte", "3/12", "2001", "Rock"]
    assert id3["WOAS"].url == "https://youtu.be/1" and "TCMP" not in id3 and id3.getall("APIC")

    mp4 = MP4(m4a).tags
    assert [mp4[k][0] for k in ("\xa9nam", "\xa9ART", "aART", "\xa9alb", "\xa9day", "\xa9gen", "\xa9cmt")] == [
        "Song", "B feat. C", "B", "Platte", "2001", "Rock", "https://youtu.be/1"]
    assert mp4["trkn"] == [(3, 12)] and "cpil" not in mp4 and mp4["covr"]


def test_rewriting_replaces_old_tags(silent):
    m4a = silent("m4a")
    write_tags(m4a, album_song())
    write_tags(m4a, Item(id="1", url="", mode=MUSIK, title="Neu", artist="A"))
    tags = MP4(m4a).tags
    assert tags["\xa9nam"] == ["Neu"] and "\xa9alb" not in tags and "trkn" not in tags
