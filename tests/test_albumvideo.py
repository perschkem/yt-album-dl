import json
import os
import time

import numpy as np
import pytest

from ytdl import albumvideo
from ytdl.activity import Activity
from ytdl.albumvideo import AlbumCache
from ytdl.config import Config
from ytdl.metadata import MUSIK, Item
from ytdl.split import FPS
from ytdl.status import Status

DURATION = 300.0


@pytest.fixture()
def cfg(tmp_path):
    return Config(musik_dir=tmp_path / "Musik", podcast_dir=None, data_dir=tmp_path / "data", bitrate=320,
                  host="", port=0, ffmpeg_location=None)


def quiet_at(*seconds):
    """Lautstärkeverlauf über DURATION: laut, mit 2 s Stille an den angegebenen Stellen."""
    env = np.full(int(DURATION * FPS), -10.0)
    for sec in seconds:
        env[int(sec * FPS) - 10:int(sec * FPS) + 10] = -70.0
    return env


@pytest.fixture()
def cached(cfg):
    """Analysiertes Video im Zwischenspeicher: Audio, Vorschaubild, Lautstärkeverlauf, Metadaten."""
    cache = AlbumCache(cfg, "vid")
    cache.save_meta({"id": "vid", "url": "https://youtu.be/vid", "title": "Band - Platte", "duration": DURATION})
    (cache.folder / "audio.m4a").write_bytes(b"audio")
    (cache.folder / "audio.webp").write_bytes(b"bild")
    np.save(cache.folder / "envelope.npy", quiet_at(100, 200))
    return cache


def test_cache_rejects_bad_ids(cfg):
    for bad in ("../etc", "a/b", "", "x" * 65, "bad!id"):
        with pytest.raises(ValueError, match="Ungültige"):
            AlbumCache(cfg, bad)


def test_cache_files(cached):
    assert cached.audio.name == "audio.m4a" and cached.thumbnail.name == "audio.webp" and cached.video is None
    (cached.folder / "video.mp4.part").write_bytes(b"x")
    assert cached.video is None
    (cached.folder / "video.mp4").write_bytes(b"x")
    assert cached.video.name == "video.mp4"


def test_meta_roundtrip_and_missing(cfg, cached):
    assert cached.meta()["title"] == "Band - Platte"
    with pytest.raises(ValueError, match="nicht analysiert"):
        AlbumCache(cfg, "neu").meta()


def test_envelope_from_cache_and_missing_audio(cfg, cached):
    assert cached.has_envelope and len(cached.envelope()) == DURATION * FPS
    empty = AlbumCache(cfg, "leer")
    empty.folder.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="Audio fehlt"):
        empty.envelope()


def test_envelope_is_computed_once(cfg, monkeypatch):
    cache = AlbumCache(cfg, "neu")
    cache.folder.mkdir(parents=True)
    (cache.folder / "audio.webm").write_bytes(b"x")
    calls = []
    monkeypatch.setattr(albumvideo, "envelope", lambda audio, on_progress: calls.append(audio) or np.zeros(5))
    cache.envelope()
    cache.envelope()
    assert len(calls) == 1 and cache.has_envelope


def test_cleanup_removes_old_caches(cfg, cached):
    old = AlbumCache(cfg, "alt")
    old.save_meta({})
    past = time.time() - (albumvideo.CACHE_DAYS + 1) * 86400
    os.utime(old.folder, (past, past))
    AlbumCache.cleanup(cfg)
    assert not old.folder.exists() and cached.folder.exists()


def test_fetch_audio_downloads_once(cfg, monkeypatch):
    calls = []

    def fake_download(url, outtmpl, fmt, on_progress, **extra):
        calls.append(url)
        (outtmpl.parent / "audio.webm").write_bytes(b"x")

    monkeypatch.setattr(albumvideo, "ytdlp_download", fake_download)
    cache = AlbumCache(cfg, "neu")
    assert cache.fetch_audio("https://youtu.be/neu").name == "audio.webm"
    assert cache.fetch_audio("https://youtu.be/neu").name == "audio.webm"
    assert calls == ["https://youtu.be/neu"]


def test_fetch_video_fails_clearly(cfg, monkeypatch):
    monkeypatch.setattr(albumvideo, "ytdlp_download", lambda *a, **kw: None)
    with pytest.raises(RuntimeError, match="Video konnte nicht geladen werden"):
        AlbumCache(cfg, "neu").fetch_video("https://youtu.be/neu")


# ---------- Analyse ----------

@pytest.fixture()
def offline(monkeypatch):
    """analyze ohne Netz: yt-dlp, ffmpeg und OCR ersetzt; info lässt sich je Test anpassen."""
    info = {"id": "vid", "webpage_url": "https://youtu.be/vid", "title": "Band - Platte (Full Album)",
            "duration": DURATION, "channel": "Band"}
    used = {"frames": 0, "comments": 0, "frame_result": ([], [])}

    def fake_extract(url, **kw):
        if kw.get("getcomments"):
            used["comments"] += 1
            return {"comments": [{"text": "kein Zeitstempel"}]}
        return info

    def fake_frames(info, duration, on_progress=None):
        used["frames"] += 1
        return used["frame_result"]

    def fake_download(url, outtmpl, fmt, on_progress, **extra):
        (outtmpl.parent / "audio.m4a").write_bytes(b"x")

    monkeypatch.setattr(albumvideo, "extract_info", fake_extract)
    monkeypatch.setattr(albumvideo, "tracklist_from_frames", fake_frames)
    monkeypatch.setattr(albumvideo, "ytdlp_download", fake_download)
    monkeypatch.setattr(albumvideo, "envelope", lambda audio, on_progress: quiet_at(100, 200))
    used["info"] = info
    return used


def steps(act):
    return [(s["label"], s["state"]) for s in act.log()]


def test_analyze_uses_description_and_skips_later_sources(cfg, offline):
    offline["info"]["description"] = "0:00 Eins\n1:39 Zwei\n3:21 Band - Drei"
    act = Activity(id="a", kind="test")
    result = albumvideo.analyze("https://youtu.be/vid", cfg, act)
    assert result["source"] == "description" and result["source_label"] == "Zeitstempel in der Beschreibung"
    assert [t["title"] for t in result["tracks"]] == ["Eins", "Zwei", "Drei"]
    assert result["tracks"][1]["start"] == pytest.approx(100, abs=1)  # auf die Pause gerückt
    assert offline["frames"] == offline["comments"] == 0
    assert steps(act)[3:] == [
        ("YouTube-Kapitel", Status.NOTHING), ("Zeitstempel in der Beschreibung", Status.DONE),
        ("Trackliste im Videobild (OCR)", Status.SKIPPED), ("Zeitstempel in Kommentaren", Status.SKIPPED),
        ("Grenzen auf Pausen ausrichten", Status.DONE)]
    assert AlbumCache(cfg, "vid").meta()["url"] == "https://youtu.be/vid"
    assert result["album"] == "Platte" and result["audio_url"] == "/api/album/vid/audio" and result["peaks"]


def test_analyze_chapters_are_not_snapped(cfg, offline):
    offline["info"]["chapters"] = [{"start_time": 0, "end_time": 150, "title": "A"},
                                   {"start_time": 150, "end_time": DURATION, "title": "B"}]
    act = Activity(id="a", kind="test")
    result = albumvideo.analyze("https://youtu.be/vid", cfg, act)
    assert result["source"] == "chapters" and [t["start"] for t in result["tracks"]] == [0, 150]
    assert "Grenzen auf Pausen ausrichten" not in [label for label, _ in steps(act)]


def test_analyze_falls_back_to_silence_and_artist_from_image(cfg, offline):
    offline["frame_result"] = ([], ["DIRE STRAITS", "Brothers in Arms"])
    act = Activity(id="a", kind="test")
    result = albumvideo.analyze("https://youtu.be/vid", cfg, act)
    assert result["source"] == "silence" and len(result["tracks"]) == 3
    assert result["artist"] == "Dire Straits" and result["hints"] == ["DIRE STRAITS", "Brothers in Arms"]
    assert offline["frames"] == offline["comments"] == 1
    assert ("Pausenerkennung im Audio", Status.DONE) in steps(act)


def test_redetect_with_count(cfg, cached):
    result = albumvideo.redetect(cfg, "vid", 3, 1.0, 25.0, "Band")
    assert result["source"] == "silence" and len(result["tracks"]) == 3
    assert all(t["artist"] == "Band" for t in result["tracks"])


def test_from_text_titles_only(cfg, cached):
    result = albumvideo.from_text(cfg, "vid", "1. Eins\n2. Zwei\n3. Gast - Drei", "Band")
    assert result["source"] == "text"
    assert [(t["artist"], t["title"]) for t in result["tracks"]] == [("Band", "Eins"), ("Band", "Zwei"),
                                                                      ("Gast", "Drei")]
    with pytest.raises(ValueError, match="Keine Titel"):
        albumvideo.from_text(cfg, "vid", "   \n", "Band")


def test_scan_overlays_uses_cached_video(cfg, cached, monkeypatch):
    from ytdl.split import Segment

    (cached.folder / "video.mp4").write_bytes(b"x")
    monkeypatch.setattr(albumvideo, "ytdlp_download", lambda *a, **kw: pytest.fail("Video ist zwischengespeichert"))
    monkeypatch.setattr(albumvideo, "overlay_titles",
                        lambda video, duration, on_progress: [Segment(0, 105, "Eins"), Segment(105, DURATION, "Zwei")])
    act = Activity(id="a", kind="test")
    result = albumvideo.scan_overlays(cfg, "vid", "Band", act)
    assert result["source"] == "overlay" and result["tracks"][1]["start"] == pytest.approx(100, abs=1)
    assert act.steps[0].detail == "aus dem Zwischenspeicher"


def test_build_items_sorted_and_numbered(cfg, cached):
    tracks = [{"start": 200, "title": "Drei", "artist": ""}, {"start": 0, "title": " ", "artist": "Gast"},
              {"start": 100, "title": "Zwei", "artist": "", "on_conflict": "skip"}]
    items = albumvideo.build_items(cfg, "vid", "Platte", "Band", "2001", "", tracks)
    assert [i.id for i in items] == ["vid-01", "vid-02", "vid-03"]
    assert [(i.title, i.artist, i.start, i.end) for i in items] == [
        ("Track 1", "Gast", 0.0, 100.0), ("Zwei", "Band", 100.0, 200.0), ("Drei", "Band", 200.0, DURATION)]
    assert items[1].on_conflict == "skip" and items[0].track_total == 3 and items[0].source_title == "Band - Platte"


def test_cut_track_needs_cached_audio(cfg):
    item = Item(id="vid-01", url="", mode=MUSIK, title="T", artist="A", source_id="weg", start=0.0, end=1.0)
    with pytest.raises(RuntimeError, match="Audio fehlt"):
        albumvideo.cut_track(item, cfg, lambda *a: None)


def test_meta_is_utf8_json(cached):
    cached.save_meta({"title": "Schildkröte"})
    assert json.loads((cached.folder / "meta.json").read_text(encoding="utf-8")) == {"title": "Schildkröte"}


def test_analyze_in_english(cfg, offline):
    from ytdl import i18n

    offline["info"]["description"] = "0:00 One\n1:39 Two\n3:21 Three"
    act = Activity(id="a", kind="test")
    i18n.configure("en")
    try:
        result = albumvideo.analyze("https://youtu.be/vid", cfg, act)
    finally:
        i18n.configure("de")
    assert result["source_label"] == "Timestamps in the description"
    assert steps(act)[3:6] == [("YouTube chapters", Status.NOTHING), ("Timestamps in the description", Status.DONE),
                               ("Track list in the video image (OCR)", Status.SKIPPED)]
    assert act.steps[4].detail == "3 tracks found" and act.steps[5].detail == "not needed"


def test_missing_cached_audio_is_permanent(cfg):
    from ytdl.errors import PermanentError

    item = Item(id="vid-01", url="", mode=MUSIK, title="T", artist="A", source_id="weg", start=0.0, end=1.0)
    with pytest.raises(PermanentError):
        albumvideo.cut_track(item, cfg, lambda *a: None)
