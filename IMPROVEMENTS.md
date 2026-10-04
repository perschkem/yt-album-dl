# Verbesserungen

## Design: Schildkröten-Bilder einbauen

Das Schildkröten-Theme ist umgesetzt (Farben, Pixel-Schrift, Pixel-Rahmen, laufende Schildkröte auf dem
Fortschrittsbalken, helle und dunkle Variante). Es fehlen noch die Bilder für die einzelnen Situationen –
sie werden mit einem externen Tool erstellt und kommen wegen dessen Rate-Limit **nach und nach**.
Bis dahin zeigt die Oberfläche eine Pixel-Platzhalter-Schildkröte.

Welche Bilder es gibt und welche fehlen, steht in **[DESIGN.md](DESIGN.md)**. Neues Bild einbauen:
Datei nach `ytdl/static/img/turtles/` legen und in `TURTLES` in `ytdl/static/app.js` eintragen.
