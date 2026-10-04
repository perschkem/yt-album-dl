import numpy as np

from ytdl.split import FPS, Segment, detect_boundaries, parse_titles, parse_tracklist, peaks, snap


def synthetic(track_lengths, pause=2.0, loud=-12.0, quiet=-70.0):
    """Hüllkurve: laute Titel, getrennt durch Pausen. Liefert (Hüllkurve, erwartete Pausenmitten)."""
    rng = np.random.default_rng(0)
    parts, centers, t = [], [], 0.0
    for i, length in enumerate(track_lengths):
        parts.append(loud + rng.normal(0, 2, int(length * FPS)))
        t += length
        if i < len(track_lengths) - 1:
            parts.append(np.full(int(pause * FPS), quiet))
            centers.append(t + pause / 2)
            t += pause
    return np.concatenate(parts), centers


def test_parse_ocr_tracklist():
    text = "Best\nDIRE STRAITS\n[00:00:00] - 01.Erster\n[00:05:48] - 02.Zweiter\n[00:09:58] - 03.Dritter"
    segs = parse_tracklist(text, 900)
    assert [(s.start, s.end, s.title) for s in segs] == [
        (0, 348, "Erster"), (348, 598, "Zweiter"), (598, 900, "Dritter")]


def test_parse_tracklist_time_last_and_numbering():
    segs = parse_tracklist("1. Intro 0:00\n2. Zwei - 3:10\n3. Drei (7:45)", 600)
    assert [(s.start, s.title) for s in segs] == [(0, "Intro"), (190, "Zwei"), (465, "Drei")]


def test_parse_tracklist_rejects_noise():
    assert parse_tracklist("Danke fürs Zuhören! Bei 3:20 ist mein Lieblingsteil", 600) == []
    assert parse_tracklist("0:00 A\n1:00 B\n99:00 C", 600) == []  # Zeitstempel hinter dem Ende


def test_parse_titles():
    assert parse_titles("1. Eins\n2) Zwei\n\n- Drei") == ["Eins", "Zwei", "Drei"]


def test_detect_boundaries_auto():
    env, centers = synthetic([200, 180, 240, 150])
    cuts = detect_boundaries(env)
    assert len(cuts) == 3
    assert all(abs(c - e) < 1.5 for c, e in zip(cuts, centers))


def test_detect_boundaries_with_count_finds_shallow_gaps():
    # Überblendungen: Lautstärke sinkt nur leicht – automatische Erkennung findet nichts, mit Anzahl schon
    env, centers = synthetic([200, 180, 240], quiet=-30.0)
    assert detect_boundaries(env) == []
    cuts = detect_boundaries(env, count=3)
    assert len(cuts) == 2 and all(abs(c - e) < 1.5 for c, e in zip(cuts, centers))


def test_snap_moves_rounded_timestamps_into_pause():
    env, centers = synthetic([200, 180])
    segs = snap([Segment(0, 199), Segment(199, 382)], env)
    assert abs(segs[1].start - centers[0]) < 1.5 and segs[0].end == segs[1].start


def test_peaks_scaled():
    env, _ = synthetic([100, 100])
    values = peaks(env, points=50)
    assert len(values) <= 50 and max(values) == 1.0 and min(values) >= 0


def test_cut_and_tag_m4a(tmp_path):
    import shutil
    import subprocess

    import pytest
    from mutagen.mp4 import MP4

    from ytdl.metadata import MUSIK, Item
    from ytdl.split import cut
    from ytdl.tagger import write_tags

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg fehlt")
    source = tmp_path / "audio.m4a"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                    "-c:a", "aac", str(source)], check=True)
    target = tmp_path / "track.m4a"
    cut(source, 1.0, 4.0, target, 320)
    item = Item(id="1", url="https://x", mode=MUSIK, title="T", artist="A", album="Al", album_artist="Various Artists",
                track_no=2, track_total=9, year="2001")
    write_tags(target, item)
    audio = MP4(target)
    assert 2.8 < audio.info.length < 3.2
    assert audio.tags["\xa9nam"] == ["T"] and audio.tags["aART"] == ["Various Artists"]
    assert audio.tags["trkn"] == [(2, 9)] and audio.tags["cpil"] is True
