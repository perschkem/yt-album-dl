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
