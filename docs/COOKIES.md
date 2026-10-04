# YouTube-Anmeldung (Cookies) einrichten

Lädt man viele Videos in kurzer Zeit, meldet YouTube manchmal:

> Sign in to confirm you’re not a bot

Die Sperre gilt für deine Internetverbindung und hebt sich meist nach einigen Stunden von selbst. Wer nicht
warten will, hinterlegt in yt-album-dl eine **YouTube-Anmeldung in Form von Cookies**.

**yt-album-dl verwendet die Cookies nur, wenn YouTube eine Bot-Prüfung verlangt.** Dann wird der Aufruf sofort
mit Anmeldung wiederholt und eine Stunde lang mit Cookies geladen, danach wieder ohne. Oben auf der Seite
erscheint dazu ein Hinweis, und in der Historie ist bei jedem Titel vermerkt, ob er mit Anmeldung geladen wurde.

---

## Bevor du anfängst

- **Nimm am besten ein Zweitkonto.** Mit Cookies kann YouTube die Downloads deinem Konto zuordnen. Ein eigenes,
  kostenloses Google-Konto nur für yt-album-dl ist die sichere Wahl.
- **Die Cookie-Datei ist wie ein Passwort.** Wer sie hat, ist in diesem YouTube-Konto angemeldet. Nicht
  weitergeben, nicht hochladen, nirgends einchecken. (Im Projektordner ist sie per `.gitignore` geschützt –
  speichere sie trotzdem lieber woanders, z.B. in deinen Dokumenten.)
- **Cookies laufen ab.** Nach ein paar Wochen oder wenn du dich abmeldest, funktionieren sie nicht mehr. Dann
  einfach neu exportieren (siehe [Erneuern](#cookies-erneuern)).

---

## Weg 1: cookies.txt exportieren (empfohlen)

Funktioniert mit jedem Browser und auch unter Windows mit WSL.

### 1. Browser-Erweiterung installieren

Empfohlen: **„Get cookies.txt LOCALLY“** – quelloffen und arbeitet nur lokal auf deinem Rechner, ohne Daten zu
verschicken.

- **Firefox:** Menü ☰ → *Add-ons und Themes* → nach `Get cookies.txt LOCALLY` suchen → *Zu Firefox hinzufügen*
- **Chrome, Edge, Brave, Opera, Vivaldi:** Chrome Web Store öffnen (Edge: *Erweiterungen* → *Erweiterungen für
  Microsoft Edge abrufen* bzw. Chrome Web Store zulassen) → nach `Get cookies.txt LOCALLY` suchen → *Hinzufügen*

> ⚠️ **Achtung bei ähnlichen Namen:** Nimm die Variante mit **„LOCALLY“** im Namen. Eine ältere Erweiterung
> namens „Get cookies.txt“ (ohne LOCALLY) wurde aus dem Chrome Web Store entfernt, weil sie Daten
> weitergeschickt hat.

Damit die Erweiterung im nächsten Schritt funktioniert, muss sie **im privaten Fenster erlaubt** sein:

- **Firefox:** Add-ons → *Get cookies.txt LOCALLY* → *In privaten Fenstern ausführen* → *Erlauben*
- **Chrome/Edge/Brave:** Erweiterungen verwalten → *Get cookies.txt LOCALLY* → *Details* → *Im Inkognito-Modus
  zulassen* (Edge: *Im InPrivate-Modus zulassen*) einschalten

### 2. In einem privaten Fenster bei YouTube anmelden

YouTube erneuert die Cookies einer offenen Sitzung laufend. Exportierst du aus deinem normalen Browserfenster,
werden die exportierten Cookies deshalb oft nach kurzer Zeit ungültig. Mit einem privaten Fenster, das du gleich
danach schließt, bleiben sie deutlich länger gültig.

1. **Privates Fenster** öffnen: Firefox *Strg+Umschalt+P*, Chrome/Brave *Strg+Umschalt+N*, Edge
   *Strg+Umschalt+N* (InPrivate). Auf dem Mac ⌘ statt Strg.
2. Auf **youtube.com** gehen und dich anmelden (am besten mit dem Zweitkonto).
3. In **demselben Tab** die Adresse **`https://www.youtube.com/robots.txt`** öffnen. Das ist eine schlichte
   Textseite, auf der YouTube die Cookies nicht mehr anfasst.

### 3. Cookies exportieren

1. Auf das Symbol der Erweiterung klicken (ggf. erst über das Puzzle-Symbol 🧩 anheften).
2. Als Format **Netscape** lassen und **Export** wählen. Die Datei heißt z.B. `www.youtube.com_cookies.txt`.
3. Die Datei an einen festen Ort verschieben, z.B.
   - Windows: `C:\Users\anna\Documents\yt-album-dl\youtube-cookies.txt`
   - macOS: `/Users/anna/Documents/yt-album-dl/youtube-cookies.txt`
   - Linux: `/home/anna/Dokumente/yt-album-dl/youtube-cookies.txt`
4. **Das private Fenster sofort schließen** – ohne dich vorher abzumelden. (Abmelden würde die exportierten
   Cookies ungültig machen.)

### 4. In yt-album-dl eintragen

1. yt-album-dl öffnen → oben rechts **⚙ Einstellungen**
2. Unter **YouTube-Anmeldung** bei **cookies.txt** den Pfad eintragen – unter WSL ganz normal als Windows-Pfad,
   z.B. `C:\Users\anna\Documents\yt-album-dl\youtube-cookies.txt`
3. **Speichern.** yt-album-dl prüft, ob die Datei existiert und im richtigen Format ist.

Fertig. Steht in der Download-Liste gerade „pausiert“, klicke auf **„Jetzt fortsetzen“**.

---

## Weg 2: Cookies direkt aus dem Browser lesen

yt-album-dl kann die Cookies auch selbst aus dem Browser lesen. Dann musst du nichts exportieren, die Cookies
sind aber an dein normales Browserprofil gebunden.

| System | So geht's |
|---|---|
| **macOS / Linux** | Bei **… oder aus Browser** den Namen eintragen: `firefox`, `chrome`, `chromium`, `edge`, `brave`, `opera`, `vivaldi` oder (macOS) `safari` |
| **Windows mit WSL** | Nur **Firefox** funktioniert, und zwar mit dem Pfad zum Windows-Profil (siehe unten). Chrome und Edge verschlüsseln ihre Cookies mit Windows-Mitteln, an die WSL nicht herankommt. |

**Firefox-Profilpfad finden (Windows):** In Firefox `about:profiles` in die Adresszeile eingeben. Beim
Profil, das „wird verwendet“ zeigt, den **Wurzelordner** kopieren, z.B.
`C:\Users\anna\AppData\Roaming\Mozilla\Firefox\Profiles\abc123.default-release`. In yt-album-dl dann eintragen:

```
firefox:C:\Users\anna\AppData\Roaming\Mozilla\Firefox\Profiles\abc123.default-release
```

Hinweis: Manche Browser (v.a. Chrome) sperren ihre Cookie-Datei, solange sie geöffnet sind. Klappt das Lesen
nicht, den Browser schließen oder Weg 1 nehmen.

---

## Cookies erneuern

Zeigt yt-album-dl den Hinweis **„YouTube hat eine Bot-Prüfung verlangt – auch mit Anmeldung“**, sind die
Cookies meist abgelaufen. Dann Schritte 2–3 von Weg 1 wiederholen und die alte Datei durch die neue ersetzen
(gleicher Dateiname, dann musst du in den Einstellungen nichts ändern).

---

## Probleme?

| Problem | Lösung |
|---|---|
| „Datei nicht gefunden“ beim Speichern | Pfad prüfen. Im Explorer mit Umschalt+Rechtsklick auf die Datei → *Als Pfad kopieren* und ohne Anführungszeichen einfügen |
| „Keine cookies.txt im Netscape-Format“ | In der Erweiterung als Format **Netscape** wählen, nicht JSON |
| Bot-Prüfung trotz Cookies | Cookies abgelaufen oder aus dem normalen Fenster exportiert → neu exportieren wie in Weg 1 beschrieben |
| Erweiterung exportiert im privaten Fenster nichts | Erweiterung für private Fenster erlauben (Schritt 1) |
| Firefox-Profil: „Profilordner nicht gefunden“ | Den **Wurzelordner** aus `about:profiles` nehmen, nicht den „Lokalen Ordner“ |

Weitere Hintergründe: [yt-dlp-FAQ zu Cookies](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)
und [Exporting YouTube cookies](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies).
