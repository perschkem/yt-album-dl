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
- Das `Archive` (`ytdl/downloader.py`) ist schon per Lock geschützt. `_unique()` in `downloader.py` kann bei
  gleichzeitigen Titeln mit gleichem Namen kollidieren und braucht deshalb einen Lock um „Zielpfad wählen + verschieben“.
- Die Fortschrittsanzeige in der Oberfläche funktioniert bereits pro Titel. Es müssten nur mehrere Titel
  gleichzeitig den Status „lädt“ haben können.
- Die Album-Analyse (`/api/album/analyze`) blockiert aktuell eine Anfrage, bis sie fertig ist (ca. 1 Min.).
  Auch sie könnte als Hintergrund-Job mit Fortschritt laufen.
