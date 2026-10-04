import shutil

import pytest

from tests.test_botcheck import BOT
from ytdl import downloader, library
from ytdl.config import Config
from ytdl.library import Archive, Skipped
from ytdl.metadata import MUSIK, PODCAST, Item


@pytest.fixture()
def cfg(tmp_path):
    return Config(musik_dir=tmp_path / "Musik", podcast_dir=tmp_path / "Pod", data_dir=tmp_path / "data",
                  bitrate=320, host="", port=0, ffmpeg_location=None)


def song(**kw):
    return Item(id="v1", url="https://youtu.be/v1", mode=MUSIK, title="Titel", artist="Band", **kw)


def test_fetch_loads_into_work_dir(cfg, monkeypatch):
    calls = []

    def fake_download(url, outtmpl, fmt, on_progress, **extra):
        calls.append((url, fmt, extra))
        on_progress("1.0 von 2.0 MB", 50.0)
        outtmpl.parent.joinpath("source.webm").write_bytes(b"audio")

    monkeypatch.setattr(downloader, "ytdlp_download", fake_download)
    reports = []
    folder = downloader.fetch(song(audio_format="m4a"), cfg, lambda *a: reports.append(a))
    assert folder == downloader.work_dir(cfg, song()) and (folder / "source.webm").exists()
    (url, fmt, extra), = calls
    assert url == "https://youtu.be/v1" and fmt.startswith("bestaudio[ext=m4a]") and extra["writethumbnail"]
    assert reports == [("downloading", 0.0), ("downloading", 50.0, "1.0 von 2.0 MB")]


def test_fetch_removes_work_dir_on_error(cfg, monkeypatch):
    def fail(url, outtmpl, *a, **kw):
        (outtmpl.parent / "source.webm.part").write_bytes(b"x")
        raise RuntimeError(BOT)

    monkeypatch.setattr(downloader, "ytdlp_download", fail)
    with pytest.raises(RuntimeError, match="not a bot"):
        downloader.fetch(song(), cfg)
    assert not downloader.work_dir(cfg, song()).exists()


@pytest.fixture()
def workdir(cfg):
    folder = downloader.work_dir(cfg, song())
    folder.mkdir(parents=True)
    (folder / "source.webm").write_bytes(b"audio")
    (folder / "source.jpg").write_bytes(b"bild")
    return folder


@pytest.fixture()
def no_ffmpeg(monkeypatch):
    """encode kopiert nur, write_tags merkt sich das Vorschaubild."""
    tagged = []
    monkeypatch.setattr(downloader, "encode", lambda src, out, bitrate: shutil.copyfile(src, out))
    monkeypatch.setattr(library, "write_tags", lambda path, item, cover, crop: tagged.append(cover.name))
    return tagged


def test_convert_places_file_and_cleans_up(cfg, workdir, no_ffmpeg):
    reports = []
    target = downloader.convert(song(), cfg, lambda *a: reports.append(a[:2]), workdir)
    assert target.read_bytes() == b"audio" and target.suffix == ".mp3"
    assert no_ffmpeg == ["source.jpg"]  # Vorschaubild als Cover
    assert [r[0] for r in reports] == ["converting", "tagging", "done"]
    assert not workdir.exists() and Archive(cfg.data_dir, MUSIK).ids() == {"v1"}


def test_convert_keeps_work_dir_for_retry(cfg, workdir, monkeypatch):
    def broken(src, out, bitrate):
        raise RuntimeError("ffmpeg: kaputt")

    monkeypatch.setattr(downloader, "encode", broken)
    with pytest.raises(RuntimeError):
        downloader.convert(song(), cfg, None, workdir)
    assert workdir.exists()  # neuer Versuch muss nicht neu laden


def test_convert_skip_removes_work_dir(cfg, workdir, no_ffmpeg):
    item = song(on_conflict="skip")
    existing = library.final_path(item, cfg)
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"alt")
    with pytest.raises(Skipped):
        downloader.convert(item, cfg, None, workdir)
    assert not workdir.exists()


def test_convert_without_download(cfg, tmp_path):
    with pytest.raises(RuntimeError, match="fehlt"):
        downloader.convert(song(), cfg, None, tmp_path)


def test_probe_single_video(cfg, monkeypatch):
    info = {"id": "v1", "webpage_url": "https://youtu.be/v1", "title": "Band - Titel (Official Video)",
            "duration": 200, "channel": "Band"}
    monkeypatch.setattr(downloader, "extract_info", lambda url, **kw: info)
    Archive(cfg.data_dir, MUSIK).add("v1")
    result = downloader.probe("https://youtu.be/v1", MUSIK, cfg)
    assert result["title"] == info["title"] and not result["is_playlist"] and not result["album_video"]
    (entry,) = result["items"]
    assert (entry["artist"], entry["title"], entry["already"]) == ("Band", "Titel", True)


def test_probe_playlist_skips_unavailable_entries(cfg, monkeypatch):
    playlist = {"_type": "playlist", "id": "PL1", "title": "Liste",
                "entries": [{"id": "a", "url": "https://youtu.be/a"}, {"id": "b"}, None]}
    details = {"https://youtu.be/a": {"id": "a", "title": "Folge 1", "channel": "Kanal"}}

    def fake(url, **kw):
        if url == "https://pl":
            return playlist
        if url not in details:
            raise RuntimeError("Video unavailable")
        return details[url]

    monkeypatch.setattr(downloader, "extract_info", fake)
    result = downloader.probe("https://pl", PODCAST, cfg)
    assert result["is_playlist"] and [i["id"] for i in result["items"]] == ["a"]


def test_probe_playlist_stops_on_bot_check(cfg, monkeypatch):
    playlist = {"_type": "playlist", "id": "PL1", "entries": [{"id": "a"}]}

    def fake(url, **kw):
        if url == "https://pl":
            return playlist
        raise RuntimeError(BOT)

    monkeypatch.setattr(downloader, "extract_info", fake)
    with pytest.raises(RuntimeError, match="not a bot"):
        downloader.probe("https://pl", MUSIK, cfg)
