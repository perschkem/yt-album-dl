# Verbesserungen

## Geschwindigkeit: mehrere Downloads parallel

**Ist-Zustand:** `JobManager` in `ytdl/jobs.py` hat genau einen Worker-Thread. Jeder Titel läuft komplett
nacheinander durch: herunterladen → zu MP3 konvertieren → taggen → verschieben. Erst dann kommt der nächste.
Beim Album-Aufteilen gilt dasselbe für jeden Schnitt.

**Idee:**
- **Mehrere Worker-Threads** (z.B. 3–4), Anzahl per `.env` einstellbar (`PARALLEL_DOWNLOADS=3`).
  Downloads warten vor allem auf das Netzwerk, Konvertieren und Schneiden belasten die CPU (ffmpeg).
  Beides lässt sich gut parallel ausführen.
- **Pipeline statt Block:** Download und Konvertierung trennen. Während Titel 2 lädt, wird Titel 1 schon
  konvertiert. Alternativ ein Pool für Downloads (netzwerkgebunden) und einer für ffmpeg (Größe ≈ CPU-Kerne).
- **Album-Aufteilen:** Die Schnitte sind unabhängig voneinander. Ein `ProcessPoolExecutor` oder mehrere
  gleichzeitige ffmpeg-Prozesse sollten das etwa um die Zahl der CPU-Kerne beschleunigen.
- **Playlists:** Mit `concurrent_fragment_downloads` von yt-dlp lassen sich Fragmente einzelner Downloads
  parallel laden.
- **Weniger Arbeit:** Ist die Quelle schon AAC/M4A, könnte optional ohne Umkodieren als M4A gespeichert werden
  (deutlich schneller, keine Qualitätsverluste). Dann bräuchte es eine Formatwahl neben MP3.

**Worauf man achten muss:**
- Zu viele gleichzeitige Anfragen können YouTube-Drosselung oder 429-Fehler auslösen. Deshalb mit einem
  moderaten Standardwert anfangen.
- **Exponentieller Backoff pro Einheit:** Jeder Titel bzw. Schnitt (jede „Unit“) hat einen eigenen Retry-Zähler
  und eigene Wartezeit: 2 s → 4 s → 8 s → 16 s … bis zu einem Maximum (z.B. 5 Versuche, max. 2 Min.), mit
  zufälligem Jitter (±20 %), damit parallele Worker nicht alle gleichzeitig erneut anfragen. Eine wartende
  Unit blockiert dabei keinen Worker. Sie wird mit einem „nicht vor“-Zeitpunkt zurück in die Warteschlange
  gelegt, damit der Worker solange andere Titel bearbeitet. In der Oberfläche: Status „wartet (Versuch 2/5,
  in 8 s)“. Bei 429 zusätzlich global drosseln, also kurz weniger parallele Downloads zulassen.
  Siehe auch [Download-Retry](#download-retry).
- Das `Archive` (`ytdl/downloader.py`) ist schon per Lock geschützt. `_unique()` in `downloader.py` kann bei
  gleichzeitigen Titeln mit gleichem Namen kollidieren und braucht deshalb einen Lock um „Zielpfad wählen + verschieben“.
- Die Fortschrittsanzeige in der Oberfläche funktioniert bereits pro Titel. Es müssten nur mehrere Titel
  gleichzeitig den Status „lädt“ haben können.
- Die Album-Analyse (`/api/album/analyze`) blockiert aktuell eine Anfrage, bis sie fertig ist (ca. 1 Min.).
  Auch sie könnte als Hintergrund-Job mit Fortschritt laufen.

## Download-Retry

**Ist-Zustand:** Schlägt ein Titel fehl (Netzwerkabbruch, YouTube-Drosselung/429, kurzzeitig nicht verfügbar),
steht er in der Oberfläche auf „fehler“ und bleibt dort. Man muss die URL erneut prüfen und herunterladen.

**Idee:**
- **Automatisch:** Bei vorübergehenden Fehlern 2–3 neue Versuche mit wachsender Wartezeit (z.B. 5 s, 20 s, 60 s).
  yt-dlp bringt dafür schon `retries`, `fragment_retries` und `retry_sleep` mit. Zusätzlich ein eigener Retry
  um den ganzen Titel in `JobManager._worker` (`ytdl/jobs.py`).
- **Manuell:** Ein Button „Erneut versuchen“ bei fehlgeschlagenen Titeln und „Alle fehlgeschlagenen wiederholen“
  pro Job. Neuer Endpunkt, z.B. `POST /api/jobs/{job_id}/retry`, der die Tasks wieder in die Warteschlange legt.
- Dauerhafte Fehler (Video privat/gelöscht, Altersbeschränkung) nicht wiederholen, sondern verständlich anzeigen.

## „Im Ordner öffnen“ pro Download

**Ist-Zustand:** Fertige Titel zeigen nur den Pfad als Text (WSL-Pfad wie `/mnt/d/Musik/Musik/…`).

**Idee:**
- Ein Button „Im Ordner öffnen“ an jedem fertigen Titel (und pro Job für den Album-/Kanalordner).
- Der Browser darf aus Sicherheitsgründen keine lokalen Ordner öffnen. Deshalb übernimmt das der Server:
  Neuer Endpunkt, z.B. `POST /api/open` mit dem Pfad, der unter WSL den Windows-Explorer startet:
  `explorer.exe /select,"D:\Musik\…\datei.mp3"`. Dafür wird der WSL-Pfad per `wslpath -w`
  in einen Windows-Pfad umgewandelt. Mit `/select` ist die Datei gleich markiert.
- Unter reinem Linux als Fallback `xdg-open <ordner>`.
- **Sicherheit:** Nur Pfade innerhalb von `MUSIK_DIR`/`PODCAST_DIR` zulassen. Der Server läuft nur auf `127.0.0.1`.
- Zusätzlich praktisch: Windows-Pfad statt WSL-Pfad in der Oberfläche anzeigen und zum Kopieren anbieten.

## Ladeanzeigen: immer zeigen, was gerade passiert

**Ist-Zustand:** Bei der Album-Analyse steht ca. eine Minute lang nur ein Spinner mit einem pauschalen Text
(„Lade Audio und suche Trackgrenzen …“). Man sieht nicht, ob gerade geladen, OCR gemacht oder ein Kommentar
gesucht wird, und auch nicht, was bei den einzelnen Schritten herauskam. Ähnlich bei „Prüfen“ (Playlists mit
vielen Titeln) und beim Scan der Titeleinblendungen.

**Idee:**
- **Schrittweise Statusmeldungen mit Ergebnis**, z.B. bei der Album-Analyse:
  ```
  ✓ Video-Infos geladen
  ✓ Audio geladen (112 MB)
  ✓ Lautstärkeverlauf berechnet
  ✗ Keine Kapitel
  ✗ Keine Zeitstempel in der Beschreibung
  ✓ OCR: Trackliste im Bild gefunden (20 Titel, Bild 1 von 6)   ← fertig, Rest übersprungen
  ```
  oder im anderen Fall: „OCR: kein Text mit Zeitstempeln in 6 Bildern“ → „Suche in 60 Kommentaren …“ →
  „Kein Kommentar mit Trackliste“ → „Pausenerkennung: 14 Pausen gefunden“.
- **Fortschritt, wo messbar:** Download in % mit MB/Geschwindigkeit, OCR „Bild 3/6“, Einblendungs-Scan
  „Bild 120/680“, Prüfen einer Playlist „Titel 12/40“.
- **Umsetzung:** Analyse/Prüfen als Hintergrund-Job (siehe parallele Downloads), der eine Liste von Schritten
  mit Status (läuft/fertig/übersprungen/fehlgeschlagen), Detailtext und Fortschritt führt. Die Oberfläche fragt
  den Status regelmäßig ab (wie bei `/api/jobs`) oder bekommt ihn per Server-Sent Events.
- Das Schrittprotokoll nach der Analyse eingeklappt im Editor behalten („Wie wurden die Grenzen gefunden?“),
  damit man nachvollziehen kann, warum z.B. die Pausenerkennung statt OCR verwendet wurde.
- Bei Fehlern sagen, in welchem Schritt es passiert ist (z.B. „Fehler beim Lesen des Audios“ statt nur
  „ffmpeg konnte das Audio nicht lesen“).

## Album/Interpret für alle Titel festlegen – auch bei „Album in einem Video“

**Ist-Zustand:** Im Editor zum Aufteilen gibt es oben die Felder Album, Albuminterpret, Jahr und Genre.
Album, Jahr und Genre gelten beim Schneiden automatisch für alle Titel. Der **Interpret pro Titel** wird aber
nicht mitgeändert, wenn man das Feld „Albuminterpret“ ändert. Dann steht z.B. oben „Dire Straits“, in der
Tabelle aber noch der falsch erkannte Interpret aus dem Videotitel. Nur die Hinweis-Chips aus der OCR
übernehmen den Interpreten auch in die Tabelle. Bei Playlists gibt es dafür „Übernehmen“, beim Aufteilen nicht.

**Idee:**
- Wie bei Playlists eine Zeile **„Für alle übernehmen“**: Interpret, Album, Jahr, Genre auf alle Titel anwenden.
- Ändert man den Albuminterpreten, werden alle Titel mitgeändert, deren Interpret noch dem alten Wert entsprach.
  Titel mit abweichendem Interpreten (Sampler, „feat.“) bleiben unverändert.
- Checkbox **„Verschiedene Interpreten (Sampler)“**: Albuminterpret = „Various Artists“, Interpret pro Titel
  bleibt einzeln editierbar, Ablage unter `Musik/Various Artists/<Album>/`.
- Optional: Spalte „Interpret“ in der Tabelle ausblenden, solange alle Titel denselben Interpreten haben
  (übersichtlicher bei 20+ Titeln).
- Dieselbe Logik auch in der normalen Playlist-Vorschau vereinheitlichen, damit beide Ansichten gleich funktionieren.
