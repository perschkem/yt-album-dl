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

Die Oberfläche soll zum Logo passen: Pixel-Art, dunkles Nachtblau, goldene Rahmen, die Schildkröte als
Maskottchen, das in jeder Situation zeigt, was gerade passiert.

**Farben aus dem Logo:**
- Hintergrund Nachtblau `#0b0f1a`, Flächen `#13243f`
- Rahmen/Akzent Gold `#f2b134`
- Primärfarbe Schildkrötengrün `#7cb82f`
- Panzerbraun `#8b4a1f` für sekundäre Elemente
- Rot nur für Fehler (statt YouTube-Rot als Akzent)
- Dazu eine helle Variante (Pergament/Sand), damit das Theme auch im Light Mode funktioniert

**Stil:**
- Pixel-Schrift für Überschriften und Buttons (z.B. „Pixelify Sans“ oder „Silkscreen“, lokal eingebunden,
  damit es offline läuft), normale Schrift für Fließtext und Tabellen (Lesbarkeit)
- Kantige Pixel-Rahmen (gestufte Ecken per `box-shadow`) statt runder Ecken, `image-rendering: pixelated`
- Fortschrittsbalken: eine kleine Schildkröte läuft auf dem Balken mit dem Fortschritt mit
  („langsam, aber sie kommt an“)
- Lade-Spinner durch eine animierte Schildkröte ersetzen (z.B. Kopf ein-/ausfahren, 2–4 Frames)
- Logo im Kopfbereich, Favicon als vereinfachter Schildkrötenkopf (16/32 px)

**Schildkröte je Situation** (vorhanden: ✅, Rest zum Erstellen):

| Situation in der App | Schildkröte | Wo |
|---|---|---|
| Prüfen / Analyse läuft | ✅ prüft mit Lupe (`docs/turtles/pruefen.webp`) | Schrittprotokoll beim Prüfen |
| Leere Download-Liste | sitzt vor leerer Plattenkiste und wartet | „Noch keine Downloads“ |
| Download läuft | trägt einen Stapel Platten auf dem Panzer | Job-Karte, Fortschrittsbalken |
| Konvertieren | rührt in einem Kessel, aus dem Noten aufsteigen | Status „konvertiert“ |
| Album aufteilen / Schneiden | schneidet mit großer Schere eine Schallplatte in Stücke | Album-Editor, Status „schneidet“ |
| Taggen | klebt Etiketten auf Platten | Status „taggt“ |
| OCR / Trackliste im Bild | liest mit Brille ein großes Plakat mit Zeitstempeln | OCR-Schritt |
| Kommentare durchsuchen | blättert durch einen Stapel Sprechblasen | Kommentar-Schritt |
| Pausen erkennen | lauscht mit Hörrohr an einer Wellenform | Pausen-Schritt |
| Neuer Versuch (Backoff) | schläft mit „zZz“ neben einer Sanduhr | Status „neuer Versuch in 8 s“ |
| YouTube drosselt (429) | steht im Stau vor einem Tempolimit-Schild | Hinweis bei Drosselung |
| Fehler | liegt hilflos auf dem Rücken | Fehlermeldungen |
| Fertig | hört entspannt Musik, Daumen hoch | abgeschlossener Job |
| Im Ordner öffnen | schaut aus einem Ordner heraus | Button-Icon |
| Liste leeren | fegt mit einem Besen | „Liste leeren“-Button |
| Modus Musik | spielt Gitarre | Modus-Umschalter |
| Modus Podcast | spricht in ein Mikrofon | Modus-Umschalter |
| Album-Editor / Wellenform | steht als DJ am Plattenspieler | Editor-Kopf |

**Anforderungen an die Bilder**, damit sie einheitlich wirken:
- Stil wie Logo und `pruefen.webp`: gleiche Schildkröte, Pixel-Art, gleiche Farben
- **Transparenter Hintergrund** (PNG oder WebP), **ohne** runden Rahmen. Den Rahmen kann das CSS
  zeichnen, so passt die Figur auch in Buttons und Zeilen
- Quadratisch, 512×512 px. Wird für die Anzeige verkleinert (64–160 px) bzw. für Icons auf 32 px
- Für Animationen (Spinner, laufende Schildkröte): 2–4 Einzelbilder derselben Pose
- Ablage in `ytdl/static/img/turtles/`, Dateinamen nach Situation (`download.png`, `fehler.png` …)
