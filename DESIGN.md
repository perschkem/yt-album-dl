# Design: Schildkröten-Theme

Die Oberfläche soll zum Logo passen: Pixel-Art, dunkles Nachtblau, goldene Rahmen, die Schildkröte als
Maskottchen, das in jeder Situation zeigt, was gerade passiert.

<p align="center">
  <img src="docs/logo.webp" alt="Logo" width="200">
  <img src="docs/turtles/pruefen.webp" alt="Schildkröte prüft" width="200">
</p>

## Stand

Umgesetzt: Farben, Pixel-Schrift (Pixelify Sans, lokal in `ytdl/static/fonts/`, OFL-Lizenz), Pixel-Rahmen,
helle und dunkle Variante, Logo im Kopf, laufende Schildkröte auf dem Fortschrittsbalken und im
Schrittprotokoll. Für fehlende Situationsbilder springt `ytdl/static/img/turtles/platzhalter.svg` ein.

**Neues Bild einbauen:** Datei nach `ytdl/static/img/turtles/<situation>.png` legen und in `TURTLES` in
`ytdl/static/js/dom.js` eintragen (z.B. `leer: { src: "img/turtles/leer.png" }`), dann hier abhaken.
Im Code bereits verwendet: `pruefen` (Prüfen, Analyse, Konflikt-Dialog) und `leer` (leere Download-Liste).

## Farben aus dem Logo

- Hintergrund Nachtblau `#0b0f1a`, Flächen `#13243f`
- Rahmen/Akzent Gold `#f2b134`
- Primärfarbe Schildkrötengrün `#7cb82f`
- Panzerbraun `#8b4a1f` für sekundäre Elemente
- Rot nur für Fehler (statt YouTube-Rot als Akzent)
- Dazu eine helle Variante (Pergament/Sand), damit das Theme auch im Light Mode funktioniert

## Stil

- **Texte bleiben sachlich.** Das Schildkröten-Thema ist rein visuell (Bilder, Farben, Schrift, Rahmen) –
  keine verspielten Formulierungen wie „Die Schildkröte schaut sich das an“, kein Slogan.

- Pixel-Schrift für Überschriften und Buttons (z.B. „Pixelify Sans“ oder „Silkscreen“, lokal eingebunden,
  damit es offline läuft), normale Schrift für Fließtext und Tabellen (Lesbarkeit)
- Kantige Pixel-Rahmen (gestufte Ecken per `box-shadow`) statt runder Ecken, `image-rendering: pixelated`
- ✅ Fortschrittsbalken: eine kleine Schildkröte läuft auf dem Balken mit dem Fortschritt mit
- Lade-Spinner durch eine animierte Schildkröte ersetzen (z.B. Kopf ein-/ausfahren, 2–4 Frames)
- Logo im Kopfbereich, Favicon als vereinfachter Schildkrötenkopf (16/32 px)

## Schildkröten-Bilder

**Entscheidung:** Jeder Hauptbereich der Oberfläche bekommt eine eigene Schildkröte – mehr Bilder braucht es
nicht. Alles andere (Fortschrittsbalken, Ladeanzeigen in Schritten, leere Liste) nutzt weiter die kleine
Pixel-Schildkröte `ytdl/static/img/turtles/platzhalter.svg`.

Die Bilder kommen wegen des Rate-Limits des Bild-Tools nach und nach. ✅ = vorhanden, ⏳ = noch zu erstellen.

| Status | Bereich | Schildkröte | Wo sie erscheint | Datei |
|---|---|---|---|---|
| ✅ | **Prüfen** | prüft mit Lupe | Ladeanzeige beim Prüfen/Analysieren, Konflikt-Dialog | `pruefen.webp` |
| ⏳ | **Downloads** | z.B. trägt einen Stapel Platten auf dem Panzer | neben der Überschrift „Downloads“ | `downloads.webp` |
| ⏳ | **Historie** | z.B. blättert in einem dicken Plattenarchiv / Logbuch | im Kopf der Seite „Historie“ | `historie.webp` |
| ⏳ | **Einstellungen** | z.B. dreht mit einem Schraubenschlüssel an einem Plattenspieler | im Kopf des Einstellungsdialogs | `einstellungen.webp` |

## Anforderungen an die Bilder

Damit die Bilder zusammenpassen:
- Stil wie Logo und `pruefen.webp`: gleiche Schildkröte, Pixel-Art, gleiche Farben, runder Rahmen wie beim
  Prüf-Bild
- Quadratisch, mind. 512×512 px (wird auf ca. 96–140 px verkleinert angezeigt)
- Als PNG oder WebP nach `ytdl/static/img/turtles/` legen (Dateiname siehe Tabelle) und in `TURTLES` in
  `ytdl/static/js/dom.js` eintragen, z.B. `downloads: { src: "img/turtles/downloads.webp", round: true }`
