import pytest

from ytdl import library
from ytdl.config import Config
from ytdl.covers import CoverError
from ytdl.library import Archive, Skipped, choose_cover, downloaded_file, finish_track
from ytdl.metadata import MUSIK, Item


@pytest.fixture()
def cfg(tmp_path):
    return Config(musik_dir=tmp_path / "Musik", podcast_dir=tmp_path / "Pod", data_dir=tmp_path / "data",
                  bitrate=320, host="", port=0, ffmpeg_location=None)


def test_downloaded_file_separates_audio_thumbnail_and_partial(tmp_path):
    assert downloaded_file(tmp_path, "audio") is None
    (tmp_path / "audio.webm.part").write_bytes(b"x")
    (tmp_path / "audio.webp").write_bytes(b"x")
    assert downloaded_file(tmp_path, "audio") is None  # nur halbfertig + Vorschaubild
    assert downloaded_file(tmp_path, "audio", image=True).name == "audio.webp"
    (tmp_path / "audio.webm").write_bytes(b"x")
    (tmp_path / "video.mp4").write_bytes(b"x")
    assert downloaded_file(tmp_path, "audio").name == "audio.webm"
    assert downloaded_file(tmp_path, "video").name == "video.mp4"


def test_choose_cover_falls_back_to_thumbnail(cfg, tmp_path, monkeypatch):
    def broken(url, cache):
        raise CoverError("Cover konnte nicht geladen werden")

    monkeypatch.setattr(library, "fetch_cover", broken)
    reports = []
    thumb = tmp_path / "t.jpg"
    item = Item(id="x", url="", mode=MUSIK, title="T", artist="A", cover_url="https://x/c.jpg", cover_crop=False)
    assert choose_cover(item, cfg, thumb, lambda *a: reports.append(a)) == (thumb, True)
    assert "Vorschaubild" in reports[0][2]
    monkeypatch.setattr(library, "fetch_cover", lambda url, cache: tmp_path / "eigenes.jpg")
    assert choose_cover(item, cfg, thumb, lambda *a: None) == (tmp_path / "eigenes.jpg", False)
    plain = Item(id="x", url="", mode=MUSIK, title="T", artist="A")
    assert choose_cover(plain, cfg, None, lambda *a: None) == (None, True)


@pytest.fixture()
def tagged(monkeypatch):
    calls = []
    monkeypatch.setattr(library, "write_tags", lambda path, item, cover, crop: calls.append((path.name, cover, crop)))
    return calls


def test_finish_track_tags_places_and_archives(cfg, tmp_path, tagged):
    out = tmp_path / "out.mp3"
    out.write_bytes(b"audio")
    reports = []
    item = Item(id="v1", url="", mode=MUSIK, title="Titel", artist="Band")
    target = finish_track(out, item, cfg, tmp_path / "thumb.jpg", lambda *a: reports.append(a[:2]), 80.0)
    assert target == cfg.musik_dir / "Band" / "Singles" / "Band - Titel.mp3" and target.read_bytes() == b"audio"
    assert tagged == [("out.mp3", tmp_path / "thumb.jpg", True)]
    assert reports == [("taggt", 80.0), ("fertig", 100.0)]
    assert Archive(cfg.data_dir, MUSIK).ids() == {"v1"}


def test_finish_track_archives_album_cut_by_source_video(cfg, tmp_path, tagged):
    out = tmp_path / "track.mp3"
    out.write_bytes(b"x")
    item = Item(id="vid-01", url="", mode=MUSIK, title="Eins", artist="Band", album="Platte", track_no=1,
                source_id="vid", start=0.0, end=60.0)
    finish_track(out, item, cfg, None, lambda *a: None, 90.0)
    assert Archive(cfg.data_dir, MUSIK).ids() == {"vid"}


def test_finish_track_skip_does_not_archive(cfg, tmp_path, tagged):
    item = Item(id="v1", url="", mode=MUSIK, title="Titel", artist="Band", on_conflict="skip")
    existing = library.final_path(item, cfg)
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"alt")
    out = tmp_path / "out.mp3"
    out.write_bytes(b"neu")
    with pytest.raises(Skipped):
        finish_track(out, item, cfg, None, lambda *a: None, 80.0)
    assert existing.read_bytes() == b"alt" and Archive(cfg.data_dir, MUSIK).ids() == set()
