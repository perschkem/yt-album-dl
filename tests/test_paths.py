from pathlib import Path

from ytdl.config import to_local_path
from ytdl.metadata import MUSIK, PODCAST, Item
from ytdl.paths import music_path, podcast_path, sanitize

ROOT = Path("/musik")


def test_sanitize():
    assert sanitize('AC/DC: "Best" <of>?*') == "AC-DC - 'Best' of"
    assert sanitize("Name. ") == "Name"
    assert sanitize("CON") == "CON_"
    assert sanitize("   ") == "Unbekannt"
    assert len(sanitize("x" * 300)) == 120


def test_music_path_single():
    item = Item(id="1", url="", mode=MUSIK, title="Get Lucky", artist="Daft Punk feat. Pharrell Williams")
    assert music_path(item, ROOT) == ROOT / "Daft Punk/Singles/Daft Punk feat. Pharrell Williams - Get Lucky.mp3"


def test_music_path_album():
    item = Item(id="1", url="", mode=MUSIK, title="One More Time", artist="Daft Punk", album="Discovery",
                album_artist="Daft Punk", track_no=1, track_total=14, year="2001")
    assert music_path(item, ROOT) == ROOT / "Daft Punk/Discovery (2001)/01 - Daft Punk - One More Time.mp3"


def test_music_path_album_three_digit_tracks():
    item = Item(id="1", url="", mode=MUSIK, title="T", artist="A", album="B", album_artist="A",
                track_no=7, track_total=120)
    assert music_path(item, ROOT).name == "007 - A - T.mp3"


def test_podcast_path():
    item = Item(id="1", url="", mode=PODCAST, title="Folge 12: Über Software", artist="Mein Podcast",
                date="2026-01-02")
    assert podcast_path(item, Path("/pod")) == Path("/pod/Mein Podcast/2026-01-02 - Folge 12 - Über Software.mp3")


def test_windows_path_conversion():
    assert to_local_path(r"D:\Musik\Alben") == Path("/mnt/d/Musik/Alben")
    assert to_local_path("D:/Musik/") == Path("/mnt/d/Musik")
    assert to_local_path("/srv/musik") == Path("/srv/musik")


def test_music_path_various_artists():
    item = Item(id="1", url="", mode=MUSIK, title="Song", artist="Interpret B", album="Sampler 2026",
                album_artist="Various Artists", track_no=3, track_total=12)
    assert music_path(item, ROOT) == ROOT / "Various Artists/Sampler 2026/03 - Interpret B - Song.mp3"


def test_va_tags(tmp_path):
    import shutil
    import subprocess

    from mutagen.id3 import ID3

    from ytdl.tagger import write_tags

    if not shutil.which("ffmpeg"):
        return
    mp3 = tmp_path / "x.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc", "-t", "0.2", str(mp3)], check=True)
    item = Item(id="1", url="", mode=MUSIK, title="Song", artist="B", album="S", album_artist="Various Artists")
    write_tags(mp3, item)
    tags = ID3(mp3)
    assert str(tags["TPE2"]) == "Various Artists" and str(tags["TCMP"]) == "1" and str(tags["TPE1"]) == "B"


def test_target_path_uses_one_root_for_both_modes():
    from ytdl.paths import target_path

    song = Item(id="1", url="", mode=MUSIK, title="T", artist="A")
    episode = Item(id="2", url="", mode=PODCAST, title="F", artist="K", date="2026-01-02")
    assert target_path(song, ROOT) == music_path(song, ROOT)
    assert target_path(episode, ROOT) == podcast_path(episode, ROOT)


def test_win_path_is_empty_without_path():
    from ytdl.paths import win_path

    assert win_path("/mnt/d/Musik/x.mp3") == "D:\\Musik\\x.mp3"
    assert win_path(Path("/mnt/c")) == "C:\\"
    assert win_path("/srv/musik") == "/srv/musik"
    assert win_path("") == "" and win_path(None) == ""


def test_common_folder():
    from ytdl.paths import common_folder

    assert common_folder([]) == ""
    assert common_folder(["/m/A/Album/01.mp3"]) == "/m/A/Album"
    assert common_folder(["/m/A/Album/01.mp3", "/m/A/Album/02.mp3"]) == "/m/A/Album"
    assert common_folder(["/m/A/Singles/x.mp3", "/m/B/Singles/y.mp3"]) == "/m"
