# ytdl – YouTube → MP3

Lädt Musik und normale Videos (Podcasts, Vorträge …) von YouTube, konvertiert sie zu MP3 (320 kbit/s)
und legt sie sortiert und vollständig getaggt ab. Bedienung über den Browser.

## Ablage

```
D:\Musik\
  <Albuminterpret>\<Album> (<Jahr>)\01 - <Interpret> - <Titel>.mp3   ← Album/Playlist
  <Interpret>\Singles\<Interpret> - <Titel>.mp3                      ← Einzeltitel
D:\Podcasts\
  <Kanal>\<YYYY-MM-DD> - <Titel>.mp3
```

**Musik-Tags:** Titel, Interpret, Albuminterpret, Album, Tracknummer, Jahr, Genre, Cover, YouTube-URL
**Podcast-Tags:** Titel, Interpret/Album = Kanal, Datum, Genre „Podcast“, Cover, Beschreibung

## Installation (WSL / Linux)

```bash
sudo apt install ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
cp .env.example .env   # Zielordner anpassen
```

## Starten

```bash
uv run ytdl-web
```

Dann im (Windows-)Browser **http://localhost:8000** öffnen.

1. URL einfügen (Einzelvideo oder Playlist), Modus **Musik** oder **Podcast / Audio** wählen, **Prüfen**
2. Erkannte Interpreten/Titel/Alben kontrollieren und bei Bedarf direkt in der Tabelle korrigieren.
   Bei Playlists lässt sich Album/Albuminterpret/Jahr für alle Titel auf einmal setzen
   (leeres Album → Ablage als Singles).
3. **Herunterladen** – der Fortschritt wird unten angezeigt.

Bereits heruntergeladene Titel werden erkannt (Archiv in `data/`) und sind standardmäßig abgewählt.
Vorhandene Dateien werden nie überschrieben.

Hinweis: Bei einer Video-URL mit `&list=…` (z.B. aus einem Mix) wird nur das Video geladen. Für eine ganze
Playlist bitte die Playlist-URL (`…/playlist?list=…`) verwenden. YouTube-Music-Alben (`OLAK5uy_…`) werden
automatisch als Album mit Tracknummern erkannt.

## Konfiguration (`.env`)

| Variable          | Standard                    | Bedeutung                                  |
|-------------------|-----------------------------|--------------------------------------------|
| `MUSIK_DIR`       | `D:\Musik`      | Zielordner Musik (Windows-Pfade erlaubt)   |
| `PODCAST_DIR`     | `D:\Podcasts`   | Zielordner Podcasts/Audio                  |
| `BITRATE`         | `320`                       | MP3-Bitrate in kbit/s                      |
| `HOST` / `PORT`   | `127.0.0.1` / `8000`        | Webserver                                  |
| `FFMPEG_LOCATION` | –                           | Ordner mit ffmpeg, falls nicht im PATH     |
| `DATA_DIR`        | `./data`                    | Download-Archiv                            |

## Entwicklung

```bash
uv run pytest                                                 # Tests
uv run python -m ytdl.downloader <url> --mode musik --probe   # Erkennung ohne Download testen
```

YouTube ändert regelmäßig etwas – wenn Downloads fehlschlagen, hilft meist
`uv lock --upgrade-package yt-dlp && uv sync`.

Nur für Inhalte nutzen, die du herunterladen darfst.
