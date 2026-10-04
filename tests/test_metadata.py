import pytest

from ytdl.metadata import (
    apply_playlist,
    clean_channel,
    clean_title,
    music_item,
    podcast_item,
    primary_artist,
    split_artist_title,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Daft Punk - One More Time (Official Video)", "Daft Punk - One More Time"),
        ("Artist - Song [Official Music Video]", "Artist - Song"),
        ("Artist - Song (Lyrics)", "Artist - Song"),
        ("Artist - Song (Official Audio) [HD]", "Artist - Song"),
        ("Artist - Song 【Official Video】", "Artist - Song"),
        ("Artist - Song | Official Video", "Artist - Song"),
        ("Artist - Song Official Music Video", "Artist - Song"),
        ("Artist - Song (Visualizer)", "Artist - Song"),
        ("Artist - Song (Remastered 2011)", "Artist - Song (Remastered 2011)"),
        ("Artist - Song (Live at Wembley)", "Artist - Song (Live at Wembley)"),
        ("Artist - Song ft. Other", "Artist - Song feat. Other"),
        ("Artist - Song (Featuring Other)", "Artist - Song (feat. Other)"),
        ("The Buggles - Video Killed The Radio Star", "The Buggles - Video Killed The Radio Star"),
    ],
)
def test_clean_title(raw, expected):
    assert clean_title(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Daft Punk - One More Time", ("Daft Punk", "One More Time")),
        ("Daft Punk – One More Time", ("Daft Punk", "One More Time")),
        ("Daft Punk — One More Time", ("Daft Punk", "One More Time")),
        ("Daft Punk | One More Time", ("Daft Punk", "One More Time")),
        ("AC/DC - Back In Black - Remastered", ("AC/DC", "Back In Black - Remastered")),
        ('"One More Time" by Daft Punk', ("Daft Punk", "One More Time")),
        ('Rammstein "Sonne"', ("Rammstein", "Sonne")),
        ("Nur ein Titel", None),
    ],
)
def test_split_artist_title(raw, expected):
    assert split_artist_title(raw) == expected


def test_clean_channel():
    assert clean_channel("Daft Punk - Topic") == "Daft Punk"
    assert clean_channel("RammsteinVEVO") == "Rammstein"
    assert clean_channel("Rammstein Official") == "Rammstein"


def test_primary_artist():
    assert primary_artist("Calvin Harris feat. Rihanna") == "Calvin Harris"
    assert primary_artist("Daft Punk, Pharrell Williams") == "Daft Punk"
    assert primary_artist("Simon & Garfunkel") == "Simon & Garfunkel"


def test_music_item_prefers_ytdlp_fields():
    info = {
        "id": "abc",
        "webpage_url": "https://www.youtube.com/watch?v=abc",
        "title": "Get Lucky (Radio Edit)",
        "track": "Get Lucky (Radio Edit)",
        "artists": ["Daft Punk", "Pharrell Williams", "Nile Rodgers"],
        "album": "Random Access Memories",
        "release_year": 2013,
        "channel": "Daft Punk - Topic",
    }
    item = music_item(info)
    assert item.artist == "Daft Punk, Pharrell Williams, Nile Rodgers"
    assert item.title == "Get Lucky (Radio Edit)"
    assert item.album == "Random Access Memories"
    assert item.album_artist == "Daft Punk"
    assert item.year == "2013"


def test_music_item_parses_title():
    info = {"id": "x", "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
            "channel": "Rick Astley", "upload_date": "20091025"}
    item = music_item(info)
    assert (item.artist, item.title, item.year) == ("Rick Astley", "Never Gonna Give You Up", "2009")
    assert item.album == ""


def test_music_item_falls_back_to_channel():
    item = music_item({"id": "x", "title": "Sonne (Official Video)", "channel": "RammsteinVEVO"})
    assert (item.artist, item.title) == ("Rammstein", "Sonne")


def test_podcast_item():
    info = {"id": "p", "title": "Folge 12: Über Software", "channel": "Mein Podcast",
            "upload_date": "20260102", "description": "Beschreibung"}
    item = podcast_item(info)
    assert item.artist == "Mein Podcast"
    assert item.date == "2026-01-02"
    assert item.title == "Folge 12: Über Software"
    assert item.genre == "Podcast"


def test_apply_playlist_album():
    infos = [
        {"id": str(n), "title": f"Song {n}", "track": f"Song {n}", "artist": "Band",
         "album": "Platte", "release_year": 2020}
        for n in range(1, 4)
    ]
    items = [music_item(i) for i in infos]
    apply_playlist(items, {"id": "OLAK5uy_xyz", "title": "Album - Platte"})
    assert [i.track_no for i in items] == [1, 2, 3]
    assert all(i.track_total == 3 and i.album == "Platte" and i.album_artist == "Band" for i in items)


def test_apply_playlist_mixed_playlist_stays_singles():
    items = [music_item({"id": "1", "title": "A - Eins"}), music_item({"id": "2", "title": "B - Zwei"})]
    apply_playlist(items, {"id": "PLabc", "title": "Meine Mix-Playlist"})
    assert all(i.album == "" and i.track_no is None for i in items)
