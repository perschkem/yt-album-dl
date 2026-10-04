<p align="center">
  <img src="docs/logo.webp" alt="yt-album-dl Logo" width="320">
</p>

<h1 align="center">yt-album-dl</h1>

<p align="center">
  <strong>YouTube → MP3 mit sauberer Sortierung, vollständigen Tags und automatischem Aufteilen von Album-Videos.</strong>
</p>

Ein lokales Tool mit Weboberfläche: URL einfügen, erkannte Metadaten kontrollieren, herunterladen.
Musik landet getaggt und nach Interpret/Album sortiert in der Musiksammlung, Podcasts und andere Videos
nach Kanal sortiert in einem eigenen Ordner. Lange Videos, die ein ganzes Album enthalten, werden
in einzelne Titel geschnitten – die Trackgrenzen findet das Programm selbst, notfalls per OCR im Videobild.

## Funktionen

- 🎵 **Musik** – MP3 320 kbit/s, ID3-Tags (Titel, Interpret, Album, Tracknummer, Jahr, Genre, Cover),
  Dateiname immer `Interpret - Titel`
- 🎙️ **Podcasts / Audio** – normale Videos als MP3, sortiert nach Kanal und Datum
- 📀 **Playlists & Alben** – YouTube-Music-Alben werden automatisch als Album mit Tracknummern erkannt
- ✂️ **Album in einem Video aufteilen** – Trackgrenzen aus Kapiteln, Beschreibung, **Bild-OCR**,
  Kommentaren oder Pausenerkennung, mit Editor zur Kontrolle (Wellenform, Player, verschiebbare Grenzen)
- ✏️ **Vorschau vor dem Download** – erkannte Interpreten/Titel/Alben direkt in der Tabelle korrigieren
- 🧹 **Saubere Erkennung** – entfernt „(Official Video)“, „[HD]“, „(Lyrics)“ usw., vereinheitlicht „feat.“
- ⚡ **Parallel** – Downloads und Umwandeln laufen in getrennten Pools gleichzeitig; MP3 oder M4A pro Download wählbar
- 🤔 **Nachfrage bei Dubletten** – liegt ein Titel schon da: überschreiben, überspringen oder beide behalten
- 🐢 **Schildkröten-Design** – Pixel-Look passend zum Logo, Live-Updates ohne Neuladen
- 🔄 **Robust** – automatische neue Versuche mit exponentiellem Backoff pro Titel, „Erneut versuchen“-Button
- 📋 **Nachvollziehbar** – jeder Vorgang zeigt Schritt für Schritt, was gerade passiert und was gefunden wurde
- 📂 **Im Ordner öffnen** – fertige Titel direkt im Windows-Explorer anzeigen
- 🔁 **Keine Duplikate** – bereits geladene Titel werden erkannt, vorhandene Dateien nie überschrieben
- 🪟 **WSL-freundlich** – Windows-Pfade wie `D:\Musik` funktionieren direkt

## Ablage

```
Musik/
  <Albuminterpret>/<Album> (<Jahr>)/01 - <Interpret> - <Titel>.mp3   ← Album / Playlist / aufgeteiltes Video
  <Interpret>/Singles/<Interpret> - <Titel>.mp3                      ← Einzeltitel
Podcasts/
  <Kanal>/<YYYY-MM-DD> - <Titel>.mp3
```

**Musik-Tags:** Titel, Interpret, Albuminterpret, Album, Tracknummer, Jahr, Genre, Cover, YouTube-URL
**Podcast-Tags:** Titel, Interpret/Album = Kanal, Datum, Genre „Podcast“, Cover, Beschreibung

## Installation

Voraussetzungen: Linux oder WSL, Python ≥ 3.12, ffmpeg, Node.js (empfohlen – yt-dlp braucht eine
JavaScript-Umgebung für YouTube).

```bash
git clone git@github.com:maxperschke/yt-album-dl.git
cd yt-album-dl
sudo apt install ffmpeg
curl -LsSf https://astral.sh/uv/install.sh | sh   # Paketverwaltung, falls noch nicht vorhanden
uv sync
cp .env.example .env                               # Zielordner anpassen
```

## Benutzung

```bash
uv run ytdl-web
```

Dann im Browser **http://localhost:8000** öffnen (unter WSL auch im Windows-Browser).

1. URL einfügen (Einzelvideo oder Playlist), Modus **Musik** oder **Podcast / Audio** wählen, **Prüfen**
2. Erkannte Metadaten kontrollieren und bei Bedarf in der Tabelle korrigieren. Bei Playlists lassen sich
   Album, Albuminterpret und Jahr für alle Titel auf einmal setzen (leeres Album → Ablage als Singles).
3. **Herunterladen** – der Fortschritt wird pro Titel live angezeigt. Während Downloads laufen, kannst du
   weitere URLs prüfen und hinzufügen. **🧹 Liste leeren** blendet abgeschlossene Jobs aus (Dateien bleiben).

Neben dem Modus wählst du das Format: **MP3** (läuft überall) oder **M4A** (ohne Umkodieren, schneller,
Originalqualität). Liegt eine Zieldatei schon vor, fragt ein Dialog pro Titel: **Überschreiben**,
**Überspringen** oder **Beide behalten** (neue Datei als „… (2)“).

Schlägt ein Titel vorübergehend fehl (Verbindungsabbruch, YouTube-Drosselung), versucht das Programm es
automatisch erneut: nach 2 s, 4 s, 8 s … (max. 2 Min.). Andere Titel laufen in der Zwischenzeit weiter.
Nach „429 Too Many Requests“ lädt es für 2 Min. nur einen Titel gleichzeitig. Dauerhafte Fehler (privat,
gelöscht, Altersgrenze) werden nicht wiederholt. Fehlgeschlagene Titel lassen sich per Button neu starten.

Bei einer Video-URL mit `&list=…` (z.B. aus einem Mix) wird nur das Video geladen. Für eine ganze Playlist
die Playlist-URL (`…/playlist?list=…`) verwenden.

### Album in einem Video

Ist ein Musikvideo sehr lang (ab 20 Min.) oder hat es Kapitel, erscheint **„Als Album aufteilen“**.
Die Audiospur wird geladen (Zwischenspeicher in `data/cache/`, nach 7 Tagen gelöscht) und die Trackgrenzen
werden in dieser Reihenfolge gesucht:

1. YouTube-Kapitel
2. Zeitstempel in der Videobeschreibung
3. **Trackliste im Videobild** – einige Standbilder werden per OCR ([RapidOCR](https://github.com/RapidAI/RapidOCR)) gelesen
4. Zeitstempel in den Top-Kommentaren
5. Pausenerkennung im Audio

Zeitstempel werden auf die leiseste Stelle in ±3 s gerückt, damit die Schnitte sauber in der Pause liegen.

Im Editor kontrollierst du das Ergebnis:

- Wellenform mit nummerierten Markierungen – Klick springt dorthin, Markierungen lassen sich verschieben
- pro Titel **▶** (ab Start abspielen), **⇤ hier** (Start = aktuelle Position), **✕** (Grenze entfernen)
- **Grenzen neu suchen:** Pausenerkennung mit fester Titelanzahl (hilft bei Überblendungen),
  Trackliste einfügen (mit Zeitstempeln oder nur Titel), Titeleinblendungen im Video scannen (langsamer)
- **Interpret für alle übernehmen**; ändert man den Albuminterpreten, ziehen alle Titel mit dem alten
  Interpreten mit. **Verschiedene Interpreten (Sampler)** legt das Album unter `Various Artists/` ab.
- **„Wie wurden die Grenzen gefunden?“** zeigt das Protokoll der Analyse

**„Schneiden & speichern“** legt die Titel als Album mit Tracknummern und Cover ab.

## Konfiguration (`.env`)

| Variable          | Standard                    | Bedeutung                                  |
|-------------------|-----------------------------|--------------------------------------------|
| `MUSIK_DIR`       | `D:\Musik`      | Zielordner Musik (Windows-Pfade erlaubt)   |
| `PODCAST_DIR`     | `D:\Podcasts`   | Zielordner Podcasts/Audio                  |
| `AUDIO_FORMAT`    | `mp3`                       | Standardformat `mp3`/`m4a` (in der Oberfläche änderbar) |
| `BITRATE`         | `320`                       | MP3-Bitrate in kbit/s                      |
| `PARALLEL_DOWNLOADS` | `3`                      | gleichzeitige Downloads                    |
| `PARALLEL_CUTS`   | Anzahl CPU-Kerne            | gleichzeitige ffmpeg-Arbeiten (Umwandeln, Schneiden) |
| `MAX_RETRIES`     | `5`                         | neue Versuche bei vorübergehenden Fehlern  |
| `HOST` / `PORT`   | `127.0.0.1` / `8000`        | Webserver                                  |
| `FFMPEG_LOCATION` | –                           | Ordner mit ffmpeg, falls nicht im PATH     |
| `DATA_DIR`        | `./data`                    | Download-Archiv und Zwischenspeicher       |

## Projektstruktur

```
ytdl/
  web.py          FastAPI-Server und API
  downloader.py   yt-dlp: Metadaten abfragen, herunterladen, MP3 konvertieren
  metadata.py     Erkennung von Interpret/Titel/Album, Bereinigung
  paths.py        Windows-sichere Dateinamen, Zielpfade
  tagger.py       ID3-Tags und Cover (mutagen, Pillow)
  jobs.py         Warteschlange: parallele Worker, Backoff, Retry
  activity.py     Hintergrund-Vorgänge mit Schrittprotokoll
  explorer.py     „Im Ordner öffnen“ (Windows-Explorer / xdg-open)
  albumvideo.py   Album in einem Video: Analyse, Zwischenspeicher, Schnitt
  split.py        Tracklisten-Parser, Pausenerkennung, Schnitt per ffmpeg
  ocr.py          Text im Videobild lesen (RapidOCR)
  static/         Weboberfläche (HTML/CSS/JS, ohne Build-Schritt), Schrift, Schildkröten-Bilder
tests/            pytest
```

## Entwicklung

```bash
uv run pytest                                                 # Tests
uv run python -m ytdl.downloader <url> --mode musik --probe   # Erkennung ohne Download testen
```

YouTube ändert regelmäßig etwas – wenn Downloads fehlschlagen, hilft meist
`uv lock --upgrade-package yt-dlp && uv sync`.

Geplante Verbesserungen stehen in [IMPROVEMENTS.md](IMPROVEMENTS.md).

## Hinweis

Nur für Inhalte nutzen, die du herunterladen darfst – z.B. eigene, freie oder für den privaten Gebrauch
erlaubte Inhalte. Beachte die Nutzungsbedingungen von YouTube und das Urheberrecht.
