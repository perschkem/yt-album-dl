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
