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
- 📜 **Historie** – was wann von welcher URL wohin geladen wurde, mit allen Tags; durchsuchbar, CSV-Export
- 🔁 **Keine Duplikate** – bereits geladene Titel werden erkannt, vorhandene Dateien nie überschrieben
- 🪟 **WSL-freundlich** – Windows-Pfade wie `D:\Musik` funktionieren direkt
- ⚙ **Einstellungen in der Oberfläche** – Zielordner, Format, Bitrate, Parallelität; gespeichert in `.env`

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

Du brauchst: **ffmpeg** (zum Umwandeln), **git** (zum Herunterladen des Programms), **uv** (installiert Python
und alle Pakete automatisch – Python musst du nicht selbst installieren) und empfohlen **Deno** (yt-dlp braucht
für YouTube eine JavaScript-Umgebung; ohne sie fehlen manchmal Formate).

Schritt-für-Schritt-Anleitungen: [Windows (mit WSL)](#windows-mit-wsl) · [macOS](#macos) · [Linux](#linux)

**Kurzfassung für Erfahrene:**

```bash
git clone https://github.com/maxperschke/yt-album-dl.git
cd yt-album-dl
uv sync
uv run ytdl-web          # → http://localhost:8000, Zielordner unter ⚙ Einstellungen festlegen
```

> **Zugriff:** Ist das Repository privat, fragt `git clone` nach Benutzername und Passwort. Als Passwort dient dann
> ein GitHub-Token (GitHub → Settings → Developer settings → Personal access tokens), dein normales Passwort
> funktioniert dort nicht. Bei einem öffentlichen Repository entfällt das.

> Tipp: In den Anleitungen stehen Befehle in grauen Kästen. Kopiere sie einzeln (Markieren → Strg+C bzw. ⌘+C),
> füge sie im Terminal ein (Rechtsklick oder Strg+Umschalt+V bzw. ⌘+V) und drücke **Enter**.
> Wenn nach dem Passwort gefragt wird: Beim Tippen erscheinen keine Zeichen – das ist normal.

### Windows (mit WSL)

WSL („Windows-Subsystem für Linux“) ist ein kleines Linux, das Microsoft direkt in Windows mitliefert.
Das Programm läuft darin, du bedienst es ganz normal im Windows-Browser und die Musik landet in deinen
Windows-Ordnern.

**1. WSL installieren (einmalig)**

1. Klicke auf **Start**, tippe `PowerShell`, klicke mit der rechten Maustaste auf **Windows PowerShell** und wähle
   **Als Administrator ausführen**.
2. Gib diesen Befehl ein und drücke Enter:
   ```powershell
   wsl --install
   ```
3. **Starte den PC neu**, wenn du dazu aufgefordert wirst.
4. Nach dem Neustart öffnet sich ein schwarzes Fenster „Ubuntu“ (falls nicht: Start → `Ubuntu` öffnen).
   Lege dort einen **Benutzernamen** (klein, ohne Leerzeichen, z.B. `anna`) und ein **Passwort** fest.
   Merk dir das Passwort – du brauchst es gleich.

Ab jetzt passiert alles im **Ubuntu-Fenster**.

**2. Benötigte Programme installieren**

```bash
sudo apt update && sudo apt install -y ffmpeg git curl unzip
```

(Fragt nach deinem Ubuntu-Passwort.) Dann uv und Deno:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
curl -fsSL https://deno.land/install.sh | sh
```

Fragt Deno „Edit shell configs to add deno to the PATH?“, antworte mit `y` und Enter.
**Schließe danach das Ubuntu-Fenster und öffne es neu** (Start → `Ubuntu`), damit die neuen Programme gefunden werden.

**3. yt-album-dl herunterladen und einrichten**

```bash
git clone https://github.com/maxperschke/yt-album-dl.git
cd yt-album-dl
uv sync
```

`uv sync` lädt beim ersten Mal Python und alle Pakete – das dauert ein, zwei Minuten.

**4. Starten**

```bash
uv run ytdl-web
```

Öffne in deinem normalen Windows-Browser (Edge, Chrome, Firefox …) die Adresse **http://localhost:8000**.
Das Ubuntu-Fenster muss dabei offen bleiben.

**5. Zielordner festlegen**

Klicke oben rechts auf **⚙ Einstellungen** und trage deine Ordner ein – ganz normale Windows-Pfade
funktionieren, z.B. `D:\Musik` und `D:\Podcasts` (oder `C:\Users\anna\Music`). Speichern, fertig.

### macOS

**1. Terminal öffnen:** Programme → Dienstprogramme → **Terminal** (oder ⌘+Leertaste, `Terminal` tippen).

**2. Homebrew installieren** (Paketverwaltung für den Mac – überspringen, falls schon vorhanden):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Fragt nach deinem Mac-Passwort. Am Ende zeigt Homebrew unter **„Next steps“** zwei oder drei Befehle an –
kopiere sie und führe sie aus (sie machen `brew` im Terminal verfügbar).

**3. Benötigte Programme installieren:**

```bash
brew install ffmpeg git uv deno
```

**4. yt-album-dl herunterladen, einrichten und starten:**

```bash
git clone https://github.com/maxperschke/yt-album-dl.git
cd yt-album-dl
uv sync
uv run ytdl-web
```

Im Browser **http://localhost:8000** öffnen, unter **⚙ Einstellungen** die Ordner festlegen, z.B.
`/Users/anna/Music/yt-album-dl` und `/Users/anna/Music/Podcasts`. „Im Ordner öffnen“ zeigt die Datei im Finder.

### Linux

**1. Benötigte Programme installieren** – je nach Distribution:

```bash
# Ubuntu, Debian, Linux Mint
sudo apt update && sudo apt install -y ffmpeg git curl unzip
```

```bash
# Fedora (ffmpeg kommt aus RPM Fusion: https://rpmfusion.org/Configuration)
sudo dnf install -y ffmpeg git curl unzip
```

```bash
# Arch, Manjaro
sudo pacman -S --needed ffmpeg git curl unzip
```

**2. uv und Deno installieren**, danach das Terminal schließen und neu öffnen:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
curl -fsSL https://deno.land/install.sh | sh
```

**3. yt-album-dl herunterladen, einrichten und starten:**

```bash
git clone https://github.com/maxperschke/yt-album-dl.git
cd yt-album-dl
uv sync
uv run ytdl-web
```

Im Browser **http://localhost:8000** öffnen und unter **⚙ Einstellungen** die Ordner festlegen,
z.B. `/home/anna/Musik`.

### Später starten, beenden, aktualisieren

- **Starten:** Terminal (unter Windows: Start → `Ubuntu`) öffnen, dann
  ```bash
  cd yt-album-dl && uv run ytdl-web
  ```
  und im Browser http://localhost:8000 öffnen.
- **Beenden:** Im Terminal **Strg+C** drücken (auch auf dem Mac Strg, nicht ⌘). Laufende Downloads werden dabei abgebrochen.
- **Aktualisieren** (neue Version von yt-album-dl und yt-dlp – hilft auch, wenn YouTube-Downloads plötzlich
  nicht mehr klappen):
  ```bash
  cd yt-album-dl && git pull && uv lock --upgrade-package yt-dlp && uv sync
  ```

### Probleme?

| Problem | Lösung |
|---|---|
| `wsl --install` meldet einen Fehler zur Virtualisierung | Virtualisierung im BIOS/UEFI einschalten („Intel VT-x“ bzw. „AMD-V/SVM“), dann erneut versuchen |
| `uv: command not found` bzw. `Befehl nicht gefunden` | Terminal schließen und neu öffnen; unter Linux/WSL alternativ `source $HOME/.local/bin/env` |
| Browser zeigt „Seite nicht erreichbar“ | Läuft `uv run ytdl-web` noch im Terminal? Fenster offen lassen. Adresse genau `http://localhost:8000` |
| „Address already in use“ beim Start | Port belegt – in `.env` z.B. `PORT=8001` eintragen und dann http://localhost:8001 öffnen |
| Hinweis „ffmpeg wurde nicht gefunden“ | Schritt „Benötigte Programme installieren“ wiederholen |
| Downloads schlagen plötzlich fehl | Meist hat YouTube etwas geändert → siehe **Aktualisieren** oben |
| Unter Windows: Wo liegen die Dateien von Ubuntu? | Im Explorer links unter **Linux** → **Ubuntu** (oder `\\wsl$\Ubuntu` in die Adresszeile) |

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

Über **📜 Historie** im Kopfbereich siehst du jeden geladenen Titel: Zeitpunkt, Quell-URL, Zielpfad, alle Tags,
Cover-Quelle, Ergebnis (fertig/überschrieben/übersprungen/Fehler) und bei Album-Schnitten Ausschnitt und Herkunft
der Trackgrenzen. Gespeichert wird sie in `data/history.jsonl` (nicht im Repo).

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
| `MUSIK_DIR`       | – (nicht gesetzt)           | Zielordner Musik (Windows-Pfade erlaubt)   |
| `PODCAST_DIR`     | – (nicht gesetzt)           | Zielordner Podcasts/Audio                  |
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
  history.py      Download-Historie (data/history.jsonl)
  covers.py       Eigenes Cover per URL
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
