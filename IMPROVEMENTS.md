# Verbesserungen

## Design: Schildkröten-Bilder einbauen

Das Schildkröten-Theme ist umgesetzt (Farben, Pixel-Schrift, Pixel-Rahmen, laufende Schildkröte auf dem
Fortschrittsbalken, helle und dunkle Variante). Es fehlen noch die Bilder für die einzelnen Situationen –
sie werden mit einem externen Tool erstellt und kommen wegen dessen Rate-Limit **nach und nach**.
Bis dahin zeigt die Oberfläche eine Pixel-Platzhalter-Schildkröte.

Welche Bilder es gibt und welche fehlen, steht in **[DESIGN.md](DESIGN.md)**. Neues Bild einbauen:
Datei nach `ytdl/static/img/turtles/` legen und in `TURTLES` in `ytdl/static/app.js` eintragen.

## Download-Historie

**Ist-Zustand:** Es gibt nur das Archiv (`data/archive-<modus>.txt`) mit Video-IDs gegen doppelte Downloads.
Was wann wohin geladen wurde, ist nicht nachvollziehbar, und die Job-Liste geht beim Neustart verloren.

**Idee:**
- **Pro fertigem Titel einen Eintrag** in eine Historie-Datei, z.B. `data/history.jsonl` (eine JSON-Zeile pro
  Titel; liegt unter `data/` und damit nicht im Repo). Inhalt:
  - Zeitpunkt, Modus (Musik/Podcast), Format und Bitrate
  - Quell-URL, Video-ID, Original-Videotitel; bei Album-Schnitten zusätzlich Start/Ende im Video
  - Zielpfad (Linux- und Windows-Pfad), Dateigröße
  - geschriebene Tags: Interpret, Titel, Album, Albuminterpret, Tracknummer, Jahr, Genre, Cover ja/nein
  - Ergebnis: fertig / übersprungen / überschrieben / Fehler (mit Meldung), Anzahl Versuche
  - bei Album-Analysen: woher die Trackgrenzen kamen (Kapitel, OCR, Kommentar, Pausen …)
- **Ansicht in der Oberfläche:** ein Link „📜 Historie“ im Kopfbereich, der eine eigene Seite öffnet
  (z.B. `/historie`). Dort eine Tabelle, neueste zuerst, mit Suche/Filter (Interpret, Titel, Album, Modus,
  Zeitraum, nur Fehler). Pro Eintrag aufklappbare Details mit allen Tags, sowie „📂 Im Ordner öffnen“ und
  Link zum Originalvideo.
- **API:** `GET /api/history?q=…&limit=…&offset=…` liest die Datei seitenweise (neueste zuerst).
- Optional: Export als CSV, Einträge löschen bzw. Historie leeren, Hinweis wenn eine Datei inzwischen
  nicht mehr existiert.
- Die Historie ergänzt das Archiv, ersetzt es aber nicht. Das Archiv bleibt die schnelle Prüfung auf
  „schon geladen“.
