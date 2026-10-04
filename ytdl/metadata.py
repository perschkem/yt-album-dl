"""Erkennung von Interpret, Titel, Album usw. aus den yt-dlp-Infos."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass

MUSIK = "musik"
PODCAST = "podcast"

# Schlagwörter, an denen man "Müll" in Klammern erkennt: (Official Video), [HD], (Lyrics) ...
_JUNK_WORDS = (
    r"official|offizielle?s?|video|videoclip|clip|audio|lyrics?|lyric|visuali[sz]er|"
    r"hd|hq|4k|8k|uhd|1080p|720p|mv|m/v|explicit|musikvideo|music|"
    r"color coded|letra|paroles|songtext|full song|premiere"
)
_JUNK_BRACKET = re.compile(
    rf"\s*[\(\[\{{【]([^\)\]\}}】]*\b(?:{_JUNK_WORDS})\b[^\)\]\}}】]*)[\)\]\}}】]",
    re.IGNORECASE,
)
# Unbeklammertes "| Official Video", "Official Music Video" usw. am Ende.
# Ein einzelnes "Video"/"Audio" ohne Trenner bleibt stehen (könnte zum Songtitel gehören).
_JUNK_TAIL = re.compile(
    r"\s*(?:"
    r"[|/•]\s*(?:official\s+)?(?:music\s+|lyric\s+)?(?:video|audio|lyrics|visuali[sz]er|musikvideo)"
    r"|official\s+(?:music\s+|lyric\s+)?(?:video|audio)"
    r"|(?:music|lyric)\s+video"
    r")\s*$",
    re.IGNORECASE,
)
_FEAT = re.compile(r"\b(?:ft|feat|featuring)\b\.?\s*", re.IGNORECASE)
_SEPARATORS = (" - ", " – ", " — ", " ~ ", " | ")
_QUOTED_BY = re.compile(r'^["“„\'](.+?)["”“\']\s+by\s+(.+)$', re.IGNORECASE)
_ARTIST_QUOTED = re.compile(r'^(.+?)\s+["“„](.+?)["”“]\s*$')
_CHANNEL_SUFFIX = re.compile(r"\s*(?:-\s*topic|vevo|official|offiziell)\s*$", re.IGNORECASE)
_ALBUM_PREFIX = re.compile(r"^(?:album|ep|single)\s*[-–—:]\s*", re.IGNORECASE)


@dataclass
class Item:
    """Ein Titel/Video samt (editierbarer) Metadaten."""

    id: str
    url: str
    mode: str
    title: str
    artist: str = ""  # Musik: Interpret; Podcast: Kanal
    album: str = ""
    album_artist: str = ""
    track_no: int | None = None
    track_total: int | None = None
    year: str = ""
    date: str = ""  # Podcast: YYYY-MM-DD
    genre: str = ""
    description: str = ""
    thumbnail: str = ""
    duration: int | None = None
    source_title: str = ""  # Original-Videotitel (zur Kontrolle in der Oberfläche)
    # Album in einem Video: Ausschnitt [start, end) in Sekunden aus dem Video source_id
    start: float | None = None
    end: float | None = None
    source_id: str = ""
    # Pro Job wählbar; leer = AUDIO_FORMAT aus .env
    audio_format: str = ""
    # Was tun, wenn die Zieldatei schon existiert: keep_both (… (2).mp3) | overwrite | skip
    on_conflict: str = "keep_both"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in data.items() if k in fields})


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" -–—|~•")


def normalize_feat(text: str) -> str:
    """Vereinheitlicht ft./feat/featuring zu 'feat.'."""
    return _squash(_FEAT.sub("feat. ", text))


def clean_title(text: str) -> str:
    """Entfernt (Official Video), [HD], (Lyrics) usw."""
    previous = None
    while previous != text:
        previous = text
        text = _JUNK_BRACKET.sub("", text)
        text = _JUNK_TAIL.sub("", text)
    return normalize_feat(text)


def clean_channel(name: str) -> str:
    """'Daft Punk - Topic' / 'DaftPunkVEVO' → 'Daft Punk' bzw. 'DaftPunk'."""
    return _squash(_CHANNEL_SUFFIX.sub("", name or ""))


def split_artist_title(text: str) -> tuple[str, str] | None:
    """Zerlegt 'Interpret - Titel' (und Varianten). Gibt None zurück, wenn kein Muster passt."""
    text = text.strip()
    if m := _QUOTED_BY.match(text):
        return _squash(m.group(2)), _squash(m.group(1))
    for sep in _SEPARATORS:
        if sep in text:
            artist, title = text.split(sep, 1)
            if artist.strip() and title.strip():
                return _squash(artist), _squash(title)
    if m := _ARTIST_QUOTED.match(text):
        return _squash(m.group(1)), _squash(m.group(2))
    return None


def primary_artist(artist: str) -> str:
    """Hauptinterpret für den Ordner: 'A feat. B' / 'A, B' → 'A'."""
    artist = re.split(r"\s+feat\.\s+|,\s+", artist, maxsplit=1)[0]
    return _squash(artist) or "Unbekannt"


def _year(info: dict) -> str:
    if info.get("release_year"):
        return str(info["release_year"])
    for key in ("release_date", "upload_date"):
        if (value := info.get(key)) and len(str(value)) >= 4:
            return str(value)[:4]
    return ""


def _info_artist(info: dict) -> str:
    artists = info.get("artists") or info.get("creators")
    if isinstance(artists, list) and artists:
        unique = list(dict.fromkeys(a.strip() for a in artists if a and a.strip()))
        return ", ".join(unique)
    return (info.get("artist") or info.get("creator") or "").strip()


def music_item(info: dict) -> Item:
    """Erzeugt Musik-Metadaten aus einem einzelnen yt-dlp-Video-Info-Dict."""
    source_title = info.get("title") or ""
    artist = _info_artist(info)
    track = (info.get("track") or "").strip()

    if artist and track:
        title = clean_title(track)
    else:
        cleaned = clean_title(source_title)
        parsed = split_artist_title(cleaned)
        if parsed:
            artist, title = parsed
            title = clean_title(title)
        else:
            title = cleaned
            artist = artist or clean_channel(info.get("channel") or info.get("uploader") or "")

    artist = normalize_feat(artist) or "Unbekannt"
    album = _squash(info.get("album") or "")
    genre = info.get("genre") or ""
    if not genre and isinstance(info.get("genres"), list) and info["genres"]:
        genre = info["genres"][0]

    return Item(
        id=info.get("id") or "",
        url=info.get("webpage_url") or info.get("original_url") or "",
        mode=MUSIK,
        title=title or "Unbekannt",
        artist=artist,
        album=album,
        album_artist=primary_artist(artist),
        track_no=info.get("track_number"),
        year=_year(info),
        genre=genre,
        thumbnail=info.get("thumbnail") or "",
        duration=info.get("duration"),
        source_title=source_title,
    )


def podcast_item(info: dict) -> Item:
    """Erzeugt Podcast-/Audio-Metadaten aus einem yt-dlp-Video-Info-Dict."""
    upload = str(info.get("upload_date") or info.get("release_date") or "")
    date = f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}" if len(upload) == 8 else ""
    channel = clean_channel(info.get("channel") or info.get("uploader") or "") or "Unbekannt"
    source_title = info.get("title") or ""
    return Item(
        id=info.get("id") or "",
        url=info.get("webpage_url") or info.get("original_url") or "",
        mode=PODCAST,
        title=_squash(source_title) or "Unbekannt",
        artist=channel,
        album=channel,
        album_artist=channel,
        year=date[:4],
        date=date,
        genre="Podcast",
        description=(info.get("description") or "").strip(),
        thumbnail=info.get("thumbnail") or "",
        duration=info.get("duration"),
        source_title=source_title,
    )


def is_album_playlist(playlist: dict) -> bool:
    """YouTube-Music-Alben haben Playlist-IDs mit 'OLAK5uy_'."""
    return str(playlist.get("id") or "").startswith("OLAK5uy_")


def apply_playlist(items: list[Item], playlist: dict) -> None:
    """Setzt bei Album-Playlists Album, Albuminterpret und Tracknummern für alle Einträge."""
    if not items:
        return
    album_items = [i for i in items if i.album]
    album = ""
    if is_album_playlist(playlist):
        album = _ALBUM_PREFIX.sub("", playlist.get("title") or "").strip()
    elif album_items and len(album_items) == len(items) and len({i.album for i in items}) == 1:
        album = items[0].album  # alle Einträge gehören zum selben Album
    if not album:
        return

    album_artist = Counter(i.album_artist for i in items).most_common(1)[0][0]
    year = Counter(i.year for i in items if i.year).most_common(1)
    for index, item in enumerate(items, start=1):
        item.album = album
        item.album_artist = album_artist
        item.track_no = index
        item.track_total = len(items)
        if year:
            item.year = year[0][0]
