# Verbesserungen

## Pipeline mit getrennten Pools

Download (Netzwerk) und Konvertierung/Schnitt (CPU, ffmpeg) laufen pro Titel noch nacheinander im selben
Worker. Die Parallelität über mehrere Titel gleicht das meist aus. Bei sehr großen Warteschlangen wären
getrennte Pools besser: einer für Downloads, einer für ffmpeg (Größe ≈ CPU-Kerne).

## Live-Updates per Server-Sent Events

Die Oberfläche fragt Jobs und Vorgänge aktuell jede Sekunde ab (`/api/jobs`, `/api/activities/{id}`).
Mit Server-Sent Events kämen Fortschritt und Schritte sofort an, und es gäbe weniger Anfragen.

## Formatwahl pro Job in der Oberfläche

MP3 oder M4A lässt sich bisher nur global per `AUDIO_FORMAT` in `.env` einstellen. Besser wäre eine Auswahl
in der Oberfläche pro Download bzw. Album, mit `.env` als Standardwert.

## Dialog bei bereits vorhandenen Titeln

**Ist-Zustand:** Bereits geladene Titel sind in der Vorschau abgewählt. Setzt man den Haken trotzdem oder
existiert die Zieldatei schon (z.B. gleicher Name aus anderem Video), wird automatisch mit „ (2)“ daneben
gespeichert (`_unique()` in `ytdl/downloader.py`). Man wird nicht gefragt.

**Idee:** Vor dem Start prüfen, welche Zieldateien schon existieren, und einen Dialog zeigen:
- **Überschreiben** – vorhandene Datei ersetzen
- **Überspringen** („doch nicht“) – Titel nicht laden
- **Beide behalten** – neue Datei als „Titel (2).mp3“ speichern (heutiges Verhalten)

Details:
- Bei mehreren Konflikten (Playlist, Album) eine Liste mit Auswahl pro Titel plus „Für alle übernehmen“
- Neuer Endpunkt, z.B. `POST /api/conflicts` mit den geplanten Titeln → liefert vorhandene Zielpfade
  (berechnet über `target_path()`), inkl. Dateigröße/Datum zum Vergleich
- Die Entscheidung wird pro Titel mitgeschickt (`on_conflict: overwrite | skip | keep_both`) und in `place()`
  angewendet. Beim Überschreiben erst in eine temporäre Datei schreiben und dann ersetzen, damit bei einem
  Fehler nichts verloren geht.
- Gilt auch für Album-Schnitte; als Standard ohne Dialog bleibt „Beide behalten“

## „Liste leeren“-Button für Downloads

Ein Button über der Download-Liste, der die angezeigten Jobs einfach ausblendet, rein optisch.
Dateien, Archiv und laufende Downloads bleiben unberührt. Noch laufende Jobs bleiben sichtbar
(oder werden erst nach Abschluss entfernt). Umsetzung z.B. über `DELETE /api/jobs?finished=true`
oder nur im Browser über eine Liste ausgeblendeter Job-IDs.

## Design: Schildkröten-Theme

Die Oberfläche bekommt den Look des Logos: Pixel-Art, Nachtblau und Gold, die Schildkröte als Maskottchen
für jede Situation. Konzept, Farben, Stil und die Liste aller Schildkröten-Bilder stehen in **[DESIGN.md](DESIGN.md)**.

**Status:** Die Bilder werden mit einem externen Tool erstellt und kommen wegen dessen Rate-Limit **nach und
nach**. Farben, Schrift und Rahmen lassen sich schon vorher umsetzen; fehlende Bilder bekommen bis dahin
einen Platzhalter. Welche Bilder schon da sind, steht in der Tabelle in DESIGN.md.
