# Verbesserungen

## Design: Schildkröten-Bilder einbauen

Das Schildkröten-Theme ist umgesetzt (Farben, Pixel-Schrift, Pixel-Rahmen, laufende Schildkröte auf dem
Fortschrittsbalken, helle und dunkle Variante). Es fehlen noch die Bilder für die einzelnen Situationen –
sie werden mit einem externen Tool erstellt und kommen wegen dessen Rate-Limit **nach und nach**.
Bis dahin zeigt die Oberfläche eine Pixel-Platzhalter-Schildkröte.

Welche Bilder es gibt und welche fehlen, steht in **[DESIGN.md](DESIGN.md)**. Neues Bild einbauen:
Datei nach `ytdl/static/img/turtles/` legen und in `TURTLES` in `ytdl/static/app.js` eintragen.

## Zusammenfassung: nur den aktuellen Download zählen

**Ist-Zustand:** Die Zeile über der Download-Liste („⏳ 10 von 22 fertig · 12 laufen“) und ihr Gesamtbalken
zählen alle Titel aller Jobs in der Liste, auch bereits abgeschlossene. Lädt man erst ein Album mit 10 Titeln
und danach eines mit 12, steht dort „10 von 22“ und der Balken beginnt in der Mitte, obwohl das neue Album
gerade erst anfängt.

**Idee:**
- Zählen und Gesamtbalken beziehen sich nur auf die Jobs, die noch laufen. Abgeschlossene Jobs zählen nicht
  mehr mit. Beim Beispiel oben: „0 von 12 fertig“, Balken bei 0 %.
- Laufen mehrere Jobs gleichzeitig, werden nur diese zusammengezählt. Optional zusätzlich der Name des
  aktuellen Downloads, z.B. „Testalbum: 3 von 12 fertig“.
- Ist alles fertig, bleibt „✓ Alle Downloads fertig“ bzw. „⚠ … · 2 Fehler“ (bezogen auf die zuletzt
  abgeschlossenen Jobs).
- Gleiches für den Gesamtbalken eines eingeklappten Downloads: der zeigt schon nur den eigenen Job. Hier
  ist nichts zu ändern.

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
