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
    assert to_local_path(r"D:\Musik") == Path("/mnt/d/Musik/Musik")
    assert to_local_path("D:/Musik/") == Path("/mnt/d/Musik")
    assert to_local_path("/srv/musik") == Path("/srv/musik")
