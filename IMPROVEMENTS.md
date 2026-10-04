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
