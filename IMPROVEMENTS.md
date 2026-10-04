# Verbesserungen

## Design: Schildkröten-Bilder einbauen

Das Schildkröten-Theme ist umgesetzt (Farben, Pixel-Schrift, Pixel-Rahmen, laufende Schildkröte auf dem
Fortschrittsbalken, helle und dunkle Variante). Es fehlen noch die Bilder für die einzelnen Situationen –
sie werden mit einem externen Tool erstellt und kommen wegen dessen Rate-Limit **nach und nach**.
Bis dahin zeigt die Oberfläche eine Pixel-Platzhalter-Schildkröte.

Welche Bilder es gibt und welche fehlen, steht in **[DESIGN.md](DESIGN.md)**. Neues Bild einbauen:
Datei nach `ytdl/static/img/turtles/` legen und in `TURTLES` in `ytdl/static/app.js` eintragen.

## Zielordner in der Oberfläche einstellen – keine persönlichen Pfade im Repo

**Ist-Zustand:** Die Ordner für Musik und Podcasts kommen aus `MUSIK_DIR`/`PODCAST_DIR` in `.env`.
Persönliche Pfade stehen aber auch im Repo:
- `ytdl/config.py` nutzt `D:\Musik` bzw. `…\Podcasts` als Standard, wenn nichts eingestellt ist
- `.env.example` und die Konfig-Tabelle im README enthalten dieselben Pfade

**Idee:**
- **Keine Standardpfade im Code.** Ist nichts eingestellt, ist der Ordner leer bzw. „nicht gesetzt“.
  `.env.example` und README nur mit neutralen Platzhaltern (z.B. `MUSIK_DIR=` mit Kommentar und Beispiel
  `D:\Musik`). Beispiel-Pfade in Tests sind neutral oder bleiben reine Umwandlungsbeispiele.
- **Einstellungen in der Oberfläche:** ein Bereich „⚙ Einstellungen“, in dem man die Ordner für Musik und
  Podcasts eintragen kann. Windows-Pfade (`E:\…`) sind erlaubt und werden wie bisher umgewandelt. Beim
  Speichern wird geprüft, ob der Ordner existiert bzw. angelegt werden kann.
- **Speichern in `.env`:** Geänderte Werte schreibt der Server in `.env`. Andere Zeilen und Kommentare
  bleiben erhalten, nur die betroffenen Variablen werden ersetzt oder ergänzt. `.env` steht schon in
  `.gitignore`, landet also nie im Repo. Neuer Endpunkt, z.B. `PUT /api/settings`.
- Die Einstellung gilt sofort, ohne Neustart. Laufende Downloads behalten ihren ursprünglichen Zielordner.
- **Solange kein Ordner gesetzt ist,** zeigt die Oberfläche einen Hinweis mit Link zu den Einstellungen,
  und „Herunterladen“ bzw. „Schneiden & speichern“ ist gesperrt.
- Optional dieselben Einstellungen für Standardformat, Bitrate und Parallelität.

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

## Kleine Schrift ohne Pixel-Schrift

Die Pixel-Schrift ist bei kleinen Größen schwer lesbar. Sie soll nur noch für Überschriften und normale
Buttons verwendet werden. Status, Tabellenköpfe, Feldbeschriftungen, Schrittprotokoll, kleine Buttons und
Hinweise bekommen die normale Schrift.

*Vorarbeit liegt im selben Git-Stash.*

## Album-Art per URL

**Ist-Zustand:** Als Cover dient immer das YouTube-Vorschaubild (mittig quadratisch zugeschnitten).

**Idee:**
- Feld „Cover-URL“ in der Playlist-Vorschau (für alle Titel) und im Album-Editor. Optional auch pro Titel
  in der normalen Vorschau.
- Der Server lädt das Bild, prüft, ob es wirklich ein Bild ist (Typ, Größe, max. ~10 MB), und nutzt es statt
  des Vorschaubilds. Quadratisch zuschneiden nur auf Wunsch, da echte Cover meist schon quadratisch sind.
- Vorschau des Covers direkt neben dem Feld. Lässt sich das Bild nicht laden, kommt eine verständliche
  Fehlermeldung und das Vorschaubild bleibt.
- Optional: Bild per Drag & Drop oder Datei-Upload statt URL.

## „Zurücksetzen“-Knopf für Tags

Wenn man sich bei den Tags komplett vertan hat:
- Pro Titel ein Knopf „↺ Zurücksetzen“, der Interpret, Titel, Album, Tracknummer, Jahr usw. auf die
  ursprünglich erkannten Werte zurücksetzt
- Dazu ein „Alle zurücksetzen“ für die ganze Vorschau bzw. den ganzen Album-Editor (inkl. Album-Feldern,
  Sampler-Haken und Grenzen aus der Analyse), mit Rückfrage
- Umsetzung: Beim Prüfen bzw. bei der Analyse eine unveränderte Kopie der erkannten Werte merken.
  Geänderte Felder dezent markieren, damit man sieht, was von Hand angepasst wurde.

## Breitere Eingabefelder

Die Felder für Interpret, Titel und Album sind in den Tabellen zu schmal, längere Titel werden abgeschnitten.
- Tabellen-Spalten für Interpret/Titel/Album breiter, z.B. mit Mindestbreite ~220 px. Nur schmale Spalten
  (Nr., Jahr, Dauer) bleiben schmal.
- Die Seite insgesamt breiter nutzen (aktuell max. 1100 px), z.B. bis ~1400 px auf großen Bildschirmen
- Optional: Feld beim Fokussieren ausklappen oder vollen Text als Tooltip anzeigen
