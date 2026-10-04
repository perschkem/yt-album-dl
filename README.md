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

## Album in einem Video

Ist ein Musikvideo sehr lang (ab 20 Min.) oder hat es Kapitel, bietet die Vorschau **„Als Album aufteilen“** an.
Das Programm lädt die Audiospur (Zwischenspeicher in `data/cache/`, wird nach 7 Tagen gelöscht) und sucht die
Trackgrenzen in dieser Reihenfolge:

1. YouTube-Kapitel
2. Zeitstempel in der Videobeschreibung
3. **Trackliste im Videobild** – einige Standbilder werden per OCR (RapidOCR) gelesen
4. Zeitstempel in den Top-Kommentaren
5. Pausenerkennung im Audio

Zeitstempel (2–4) werden automatisch auf die leiseste Stelle in ±3 s gerückt, damit die Schnitte in der Pause liegen.

Im Editor kontrollierst du das Ergebnis: Wellenform mit verschiebbaren Markierungen, Player, ▶ pro Titel,
„⇤ hier“ setzt den Start auf die aktuelle Abspielposition. Unter **„Grenzen neu suchen“** kannst du
die Pausenerkennung mit fester Titelanzahl wiederholen (hilft bei Überblendungen), eine Trackliste einfügen
(mit Zeitstempeln oder nur Titel) oder wechselnde **Titeleinblendungen** im Video scannen lassen (langsamer).
**„Schneiden & speichern“** legt die Titel als Album ab: `Musik/<Interpret>/<Album>/01 - <Interpret> - <Titel>.mp3`.

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
