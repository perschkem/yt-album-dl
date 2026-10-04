# Verbesserungen

## Design: Schildkröten-Bilder einbauen

Das Schildkröten-Theme ist umgesetzt (Farben, Pixel-Schrift, Pixel-Rahmen, laufende Schildkröte auf dem
Fortschrittsbalken, helle und dunkle Variante). Es fehlen noch die Bilder für die einzelnen Situationen –
sie werden mit einem externen Tool erstellt und kommen wegen dessen Rate-Limit **nach und nach**.
Bis dahin zeigt die Oberfläche eine Pixel-Platzhalter-Schildkröte.

Welche Bilder es gibt und welche fehlen, steht in **[DESIGN.md](DESIGN.md)**. Neues Bild einbauen:
Datei nach `ytdl/static/img/turtles/` legen und in `TURTLES` in `ytdl/static/app.js` eintragen.

## Fortschrittsbalken beim „Infos laden“ (Prüfen)

**Ist-Zustand:** Beim Prüfen einer URL zeigt der Schritt „Video-Infos laden“ keinen Balken. yt-dlp meldet
beim Abfragen der Infos keinen Fortschritt, der Schritt hat deshalb keinen Prozentwert, und die Oberfläche
blendet den Balken dann ganz aus (`renderSteps` in `ytdl/static/app.js` zeigt ihn nur bei bekanntem Fortschritt).
Einen Balken gibt es nur bei Playlists im zweiten Schritt „Details der Titel laden“ („Titel x/y“).
Bei einem einzelnen Video sieht man also mehrere Sekunden lang nur die Schildkröte und den Text.

**Idee:**
- **Unbestimmter Balken** für Schritte ohne messbaren Fortschritt: ein Balken, über den die Schildkröte hin-
  und herläuft (oder ein laufendes Streifenmuster), damit sichtbar ist, dass etwas passiert
- Dazu die bisher vergangene Zeit anzeigen, z.B. „Video-Infos laden · 4 s“
- Bei Playlists den ersten Schritt aufteilen: erst die schnelle Liste der Einträge holen (Anzahl ist dann
  bekannt), danach wie bisher „Titel x/y“ mit echtem Fortschritt
- Gleiches gilt für andere Schritte ohne Prozentwert (z.B. „Zeitstempel in Kommentaren“ bei der Album-Analyse)
