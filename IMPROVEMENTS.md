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
