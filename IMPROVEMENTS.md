# Verbesserungen

## Umgesetzt (Oktober 2026)

- ✅ **Parallele Downloads** – `PARALLEL_DOWNLOADS` Worker für Downloads, `PARALLEL_CUTS` für Album-Schnitte.
  Download und Konvertierung verschiedener Titel überlappen sich dadurch automatisch.
- ✅ **Exponentieller Backoff pro Titel** – 2 s, 4 s, 8 s … max. 2 Min., ±20 % Jitter; wartende Titel blockieren
  keinen Worker; nach HTTP 429 vorübergehend nur ein Download; dauerhafte Fehler werden nicht wiederholt
- ✅ **Download-Retry** – automatisch (`MAX_RETRIES`) und per Button pro Titel bzw. „Fehlgeschlagene wiederholen“ pro Job
- ✅ **„Im Ordner öffnen“** – pro Titel (Datei markiert) und pro Job; Windows-Pfade anzeigen und kopieren
- ✅ **Ladeanzeigen mit Schrittprotokoll** – Prüfen, Album-Analyse, Pausensuche, Trackliste, Scan;
  Fortschritt wo messbar; Fehler nennen den Schritt; Protokoll bleibt im Editor
- ✅ **Album/Interpret für alle Titel** – auch beim Aufteilen; Sampler/Various Artists mit Compilation-Tag
- ✅ **M4A ohne Umkodieren** (`AUDIO_FORMAT=m4a`) und parallele Fragment-Downloads

## Offen

- **Pipeline mit getrennten Pools** für Netzwerk (Download) und CPU (ffmpeg) innerhalb eines Titels –
  aktuell reicht die Parallelität über mehrere Titel; lohnt sich erst bei sehr großen Warteschlangen
- **Live-Updates per Server-Sent Events** statt Abfrage im Sekundentakt
- **Formatwahl pro Job in der Oberfläche** statt nur per `.env`
