# Refactorings: Vereinfachen, Kapseln, Wiederverwenden

Ergebnis einer Durchsicht des gesamten Codes (Backend `ytdl/*.py`, Frontend `ytdl/static/*.js`).
Sortiert nach Nutzen: oben das, was Duplikate entfernt oder künftige Fehler verhindert, unten Kosmetik.
Keine der Änderungen soll das Verhalten ändern – Ausnahmen sind ausdrücklich als solche markiert.

## Stand: alles umgesetzt (2026-10-04)

| Punkte | Commit |
|---|---|
| 1.6, 1.7, 1.8, 1.9, 2.2, 2.7, 3.5 (target_path, from_dict, Logging) | `2607501` kleine gemeinsame Helfer im Backend |
| 2.1 | `44ffa00` Status-Texte zentral in `ytdl/status.py` |
| 1.5 | `c41a929` Bildverarbeitung in `covers.py` |
| 3.5 (Tagger) | `d5722d8` Tagger bestimmt die Werte einmal für beide Formate |
| 1.1, 1.2, 1.3, 1.4, 2.3 | `f4571e1` `downloader.py` aufgeteilt – `auth.py`, `ytdlp.py` und **`library.py`** (statt `files.py`: enthält auch das Taggen + Ablegen) |
| 3.5 (ffmpeg, *Verhaltensänderung*) | `2101533` `FFMPEG_LOCATION` für alle Aufrufe |
| 2.4, 3.3 | `c13e169` `AlbumCache`, Quellen als Liste |
| 2.5, 2.6 | `ae6c906` Zustandsübergänge in `Task`, einheitliche Runner-Signatur |
| 3.4 | `a29dab8` Historie: Filter, Counter, CSV-Spalten, Cache mit mtime-Prüfung |
| 3.1, 3.2 | `bd1951d` `web.py`: `settings.py`, `schemas.py`, gemeinsame Helfer |
| 3.2 (ffmpeg-Prüfung), 4.6 (IDs) – *Verhaltensänderung* | `ddf34af` Entscheidungen per Titel-ID (`decisions`), ffmpeg-Prüfung auch für Album-Schnitte |
| 4.1, 4.2 | `efa34a2` gemeinsame ES-Module, Tests mit `node --test` |
| 4.3–4.7, 5.2 | `9b403f5` doppelte Logik in `app.js` zusammengeführt |
| 5.1 | `35ff7f8` `app.js` in ES-Module aufgeteilt |

Abweichungen vom Vorschlag: Der Polling-Fallback bleibt nur für Hintergrund-Vorgänge erhalten, und zwar für den Fall,
dass der Stream abbricht (4.7). Die Titeldauer im Album-Editor wird jetzt gerundet statt abgeschnitten.
Tests: 217 pytest-Tests, davon führt einer die node-Tests in `tests/js/` aus.

---

## 1. Backend – Wiederverwendung (doppelter Code)

### 1.1 yt-dlp-Download-Muster dreifach
`downloader.fetch` (downloader.py:355–377), `albumvideo._fetch_audio` (albumvideo.py:104–118) und
`albumvideo.scan_overlays` (albumvideo.py:357–365) bauen jeweils dieselben Optionen
(`ignoreerrors: False`, `concurrent_fragment_downloads: 4`, `outtmpl`, `progress_hooks`) und dasselbe

```python
def run():
    with YoutubeDL({**_base_opts(), **opts}) as ydl:
        ydl.download([url])
with_cookie_fallback(run)
```

**Vorschlag:** eine Funktion `ytdlp_download(url, outtmpl, fmt, on_progress=None, **extra)` im Downloader-Modul,
die das Muster inkl. Cookie-Fallback kapselt. Nebeneffekt: `albumvideo` muss die privaten Namen
`_base_opts` und `_extract` nicht mehr importieren (albumvideo.py:17) – `_extract` wird öffentlich (`extract_info`).

### 1.2 Fortschritts-Hook und `_mb` doppelt
`_mb()` steht identisch in downloader.py:320 und albumvideo.py:82; die Fortschrittstext-Logik
(„x von y MB · z MB/s“) in downloader.py:346–353 und albumvideo.py:86–96.

**Vorschlag:** ein gemeinsamer `download_hook(callback)`, der aus dem yt-dlp-Dict `(detail, prozent)` berechnet
und an einen Callback übergibt. `fetch` übersetzt das auf `report("lädt", …)`, Album-Code auf `step.update(…)`.

### 1.3 Dateien im Arbeits-/Cache-Ordner finden
`_IMAGE_SUFFIXES` ist doppelt definiert (downloader.py:269, albumvideo.py:69), das Filtern von
`.part`/`.ytdl`-Resten steht an vier Stellen (downloader.py:385, albumvideo.py:75, 353, 366).

**Vorschlag:** Helfer `downloaded_file(folder, stem, image=False) -> Path | None` (z.B. in einem neuen
`ytdl/files.py`), genutzt von `convert`, `_audio_file`, `_thumbnail_file` und der Video-Suche in `scan_overlays`.

### 1.4 „Fertig machen“ eines Titels: kodieren → taggen → ablegen → Archiv
`downloader.convert` (downloader.py:390–404) und `albumvideo.cut_track` (albumvideo.py:418–427) enden gleich:
`choose_cover` → `write_tags` → `place` → `Archive(...).add(...)` → `report("fertig", 100)`.

**Vorschlag:** `finish_track(out, item, cfg, thumbnail, report, archive_id) -> Path`. Beide Stufen erzeugen nur
noch die Audiodatei (per `encode` bzw. `cut`) und rufen danach `finish_track` auf.

### 1.5 Cover quadratisch zuschneiden – doppelt, plus Kreisimport
`tagger.cover_jpeg` (tagger.py:56–67) und `covers.thumbnail_preview` (covers.py:67–74) machen beide
„schwarze Balken weg → mittig quadratisch → verkleinern → JPEG“. `covers` importiert deshalb `trim_bars` lokal aus
`tagger`, „um Kreisimporte zu vermeiden“ (covers.py:65).

**Vorschlag:** Bildverarbeitung komplett nach `covers.py` verschieben (`trim_bars`, `center_square(img)`,
`to_jpeg(img, size, quality)`); `tagger` importiert nur noch von dort. Dann gibt es keinen Kreisimport mehr.
Den ungenutzten Alias `square_cover = cover_jpeg` (tagger.py:70) entfernen.

### 1.6 Fehlermeldung aufbereiten
`str(exc).removeprefix("ERROR: ").strip()` steht in activity.py:115, jobs.py:277 und (ohne `strip`) web.py:93.

**Vorschlag:** `clean_error(exc) -> str` neben `friendly_error` im Downloader-/Auth-Modul.

### 1.7 Windows-Pfad und gemeinsamer Ordner
- `to_windows_path(Path(x)) if x else ""` steht in jobs.py:103, 145, history.py:44, 124 und web.py:113–114.
  → `win_path(value: str | Path | None) -> str` in `paths.py`, der leer zurückgibt, wenn nichts da ist.
- Den gemeinsamen Ordner mehrerer Dateien berechnen `Job.folder()` (jobs.py:125–130) und
  `History.query_groups` (history.py:120–122) jeweils selbst (leicht unterschiedlich: die Historie nimmt bei einer
  einzelnen Datei die Datei selbst). → `common_folder(paths)` in `paths.py`.

### 1.8 Label „Interpret - Titel“
`f"{item.artist} - {item.title}"` in jobs.py:97 und downloader.py:315 → Property `Item.label`.

### 1.9 Gemeinsame Felder von Musik- und Podcast-Item
`music_item` und `podcast_item` (metadata.py:173–211) befüllen `id`, `url`, `thumbnail`, `duration`,
`source_title` identisch → `_common_fields(info) -> dict`, das beide per `**` übernehmen.

---

## 2. Backend – Kapselung

### 2.1 Status-Konstanten an einer Stelle
Die Status-Texte `"fertig"`, `"fehler"`, `"übersprungen"`, `"wartet"`, `"pausiert"`, `"neuer Versuch"` … stehen
verstreut als Literale in jobs.py, downloader.py:403, albumvideo.py:426, als Konstanten in activity.py:11–15 **und**
nochmals in history.py:16. jobs.py importiert `FINISHED as DONE` aus `history` und definiert gleichzeitig ein eigenes
`FINISHED`-Tupel (jobs.py:18, 38) – derselbe Name bedeutet in zwei Modulen etwas anderes.

**Vorschlag:** ein Modul `ytdl/status.py` (oder `enum.StrEnum`), aus dem activity, jobs, history und die Runner
importieren. Die Werte bleiben gleich (das Frontend und die Historie-Dateien hängen daran).

### 2.2 Audio-Formate zentral
`("mp3", "m4a")` wird an vier Stellen geprüft: config.py:102, web.py:102, web.py:234, downloader.py:277.
→ `AUDIO_FORMATS = ("mp3", "m4a")` in `config.py`, überall verwenden.

### 2.3 Globaler `_auth`-Dict → Klasse, `downloader.py` aufteilen
`downloader.py` (431 Zeilen) ist ein Sammelbecken: ffmpeg-Check, Archiv, Cookie-/Bot-Prüfungs-Logik mit
globalem, untypisiertem `_auth`-Dict (downloader.py:59), Probe, Ablage/Konflikte, beide Download-Stufen, CLI.

**Vorschlag:**
- `ytdl/auth.py`: Klasse `YoutubeAuth` mit Attributen statt Dict-Schlüsseln (`configure`, `cookie_opts`,
  `with_cookie_fallback`, `status`, `note_bot_check`, `is_bot_check`, `BOT_CHECK_HINT`). Eine Modul-Instanz behält
  die heutige API; Tests können eine eigene Instanz erzeugen statt den globalen Zustand zu patchen.
- `ytdl/ytdlp.py`: `base_opts`, `extract_info`, `ytdlp_download` (siehe 1.1).
- `ytdl/files.py`: `place`, `conflicts`, `final_path`, `_unique`, `Archive`, `downloaded_file` (1.3).
- `downloader.py` behält `probe`, `fetch`, `convert`, `download`, `main`.

### 2.4 Album-Cache als Objekt
Alles, was in `data/cache/<video-id>/` liegt, wird über lose Funktionen angesprochen: `cache_dir`, `_audio_file`,
`_thumbnail_file`, `_envelope`, `_save_meta`, `load_meta`, die Video-Suche in `scan_overlays`. Jede öffentliche
Funktion beginnt gleich (albumvideo.py:305–307, 324–326, 350–351):

```python
act = activity or NullActivity()
folder = cache_dir(cfg, video_id)
meta = load_meta(cfg, video_id)
env = _envelope(folder, _audio_file(folder))
```

**Vorschlag:** `class AlbumCache` mit `audio`, `thumbnail`, `video`, `meta`, `envelope()`, `save_meta()`.
`AlbumCache(cfg, video_id)` prüft die ID im Konstruktor (ersetzt den `cache_dir`-Aufruf „nur zum Prüfen“ in web.py).

### 2.5 Job-Zustandsübergänge in `Task`
In jobs.py setzen viele Stellen mehrere Felder gleichzeitig per Tupel-Zuweisung
(`task.status, task.error, task.detail = "fehler", message, ""` usw.). Doppelt sind
- „Zurück auf FETCH, falls das Arbeitsverzeichnis weg ist“ (jobs.py:209–210 und 339–340, inkl. des
  `"/nonexistent"`-Tricks),
- „Neu einreihen mit `progress = STAGE_RANGE[stage][0]`“ (jobs.py:211, 292, 326, 344).

**Vorschlag:** Methoden auf `Task`: `fail(message)`, `skip(reason)`, `reset_for_retry()`, `restart_stage()`
(enthält den FETCH-Fallback), und auf `JobManager` ein `_enqueue(task)` (append + notify_all).
Dann liest sich `_failed` als Folge von Entscheidungen statt als Feldzuweisungen.

### 2.6 Einheitliche Runner-Signatur
`JobManager._run` (jobs.py:285–300) unterscheidet die Stufen, weil `convert` zusätzlich `workdir` bekommt und
`fetch` ein anderes Ergebnis liefert. Gibt man allen Runnern `(task, cfg, report)` (bzw. lässt sie ein Ergebnis-
Objekt liefern), entfällt das `if/else`, und neue Stufen brauchen keine Sonderfälle.

### 2.7 Modus-Konstanten ohne Funktions-Import
`Config.root` importiert `MUSIK` innerhalb der Methode (config.py:63), `parse_browser_spec` importiert
`to_local_path` lokal (downloader.py:136), obwohl `config` dort ohnehin oben importiert wird.
→ `MUSIK`/`PODCAST` in `config.py` (oder `modes.py`) definieren und von `metadata` re-exportieren; den lokalen
Import in `parse_browser_spec` nach oben ziehen.

---

## 3. Backend – Vereinfachung

### 3.1 `web.put_settings` tabellengesteuert
`put_settings` (web.py:188–245) ist fast 60 Zeilen mit einem eigenen Block je Feld; `get_settings`
(web.py:140–156) und `SettingsRequest` wiederholen die Feldliste ein drittes Mal, die erlaubten Bereiche stehen
zusätzlich als `min`/`max` in index.html:249–255.

**Vorschlag:** eine Tabelle `SETTINGS = {feld: Setting(env_key, validate)}`, wobei `validate(value)` entweder
`(env_wert, cfg_wert)` liefert oder `ValueError` mit der Meldung wirft. `put_settings` wird zu einer Schleife;
`get_settings` kann die Grenzen mitliefern, damit das Frontend `min`/`max` nicht selbst kennen muss.

### 3.2 Wiederkehrendes in `web.py`
- 404 für unbekannte Activity doppelt (web.py:255–257, 263–265) → `_activity_or_404(id)`.
- `CoverError → HTTPException(400)` doppelt (web.py:349–352, 358–361) → `@app.exception_handler(CoverError)`
  wie schon bei `MissingFolder`.
- `_album_call(albumvideo.cache_dir, cfg, video_id)  # ID prüfen` dreimal (web.py:404, 411, 417) → FastAPI-
  Dependency `video_id: str = Depends(valid_video_id)` oder `AlbumCache` (2.4).
- `post_job` und `album_job` filtern beide `on_conflict != "skip"` und brechen bei leerer Liste ab
  (web.py:282–285, 445–448) → `_submit(title, mode, items, empty_message)`.
  **Achtung (Verhaltensänderung):** Nur `post_job` prüft `ffmpeg_available`, `album_job` nicht – beim
  Zusammenführen würde der Check für Album-Schnitte dazukommen (was sinnvoll ist, weil `cut` ffmpeg braucht).
- `StreamingResponse(_event_stream(...), media_type=..., headers=_SSE_HEADERS)` doppelt → `_sse(request, snapshot,
  done)`; `_SSE_HEADERS` steht außerdem erst hinter seiner ersten Verwendung (web.py:326).
- `_history_filters` importiert `time` lokal (web.py:454) → oben importieren.
- Request-Modelle sind über die Datei verteilt (`CoverRequest`, `OpenRequest`, `RetryRequest`,
  `SettingsRequest` zwischen den Routen) → gesammelt oben oder in `ytdl/schemas.py`.

### 3.3 `albumvideo.analyze`: Quellen als Liste
`analyze` (albumvideo.py:188–299) wiederholt viermal das Muster
„wenn schon Segmente da: `act.skip(label, "nicht nötig")`, sonst Schritt starten, versuchen, `done`/`nothing`“.

**Vorschlag:** die Quellen als Liste `[(source, label, finder)]` (Beschreibung, Bild, Kommentar …) und eine
Schleife, die beim ersten Treffer die übrigen als übersprungen markiert. Neue Quellen sind dann ein Eintrag.

Außerdem:
- „Grenzen auf Pausen ausrichten“ + `snap` + gleiche `done`-Meldung dreimal (albumvideo.py:262–264, 330–332,
  377–380) → `_snap_step(act, segments, env, window)`.
- Das Rückgabe-Dict `{"source": s, "source_label": SOURCE_LABELS[s], "tracks": _tracks(...)}` dreimal
  (albumvideo.py:318, 344, 381) → `_result(source, segments, artist)`.

### 3.4 Historie
- `query_groups` und `to_csv` rufen `query(limit=10**9)` auf (history.py:101, 142), nur um an die gefilterte
  Liste zu kommen. → Filter in `_matching(q, mode, result, since)` auslagern, `query` macht nur noch die Seite.
- Die Ergebniszählung (history.py:117–119) ist ein `collections.Counter`.
- In `to_csv` stehen Spaltenköpfe und Werte in zwei getrennten Listen (history.py:144–156) – leicht zu
  verschieben. → Eine Liste `[(Kopf, getter)]`, aus der Kopfzeile und Zeilen erzeugt werden.
- Jeder Aufruf (auch `knows_path` für „Ordner öffnen“) liest die ganze Datei neu ein. Für die erwartete Größe ok;
  falls es wächst, wäre ein Cache mit `mtime`-Prüfung in `_all()` die einfachste Lösung.

### 3.5 Kleinigkeiten
- `paths.target_path(item, musik_root, podcast_root)` wird nur mit demselben Ordner zweimal aufgerufen
  (downloader.py:283) → `target_path(item, root)`.
- `Item.from_dict` nutzt `cls.__dataclass_fields__` → `dataclasses.fields(cls)`.
- `JobManager._record` verschluckt jeden Fehler kommentarlos (jobs.py:311–312) – wenigstens loggen.
- **Inkonsistenz:** `split.py` und `ocr.py` rufen fest `"ffmpeg"` auf, obwohl es `FFMPEG_LOCATION` gibt und
  `ffmpeg_available` diese Einstellung prüft. Ein Helfer `ffmpeg_bin(cfg)` (bzw. ein beim Start gesetzter
  Modulwert) würde das vereinheitlichen. *(Verhaltensänderung, wenn `FFMPEG_LOCATION` genutzt wird.)*
- `tagger._write_mp4` / `_write_id3` sind parallel aufgebaut; eine Zuordnung Feld → Tag-Schlüssel je Format
  wäre möglich, lohnt sich aber erst, wenn weitere Felder dazukommen.

---

## 4. Frontend – Wiederverwendung

### 4.1 Gemeinsames Modul für beide Seiten
`app.js` und `historie.js` definieren `$`, `el` und `api` jeweils selbst (app.js:1–45, historie.js:1–24) – und
sie sind schon auseinandergelaufen: `el` in der Historie filtert zusätzlich leere Strings, `api` in der Historie
kennt keine Objekt-/Listen-`detail`s – bei einem Validierungsfehler (422, `detail` ist eine Liste) zeigt sie
`[object Object]`, wo `app.js` auf „Fehler 422“ zurückfällt.

**Vorschlag:** `static/common.js` mit `$`, `el`, `api`, `turtle`, `button`, `cssName`, Zeit-/Größenformatierung;
in beiden HTML-Seiten vor dem Seitenskript laden (oder ES-Module mit `<script type="module">`).

### 4.2 Formatierung doppelt
- Zeit: `fmt` (app.js:708) und `clock` (historie.js:38).
- Dateigröße: `formatSize` (app.js:443) und `sizeText` (historie.js:44).
- CSS-Klasse aus Status: `cssName` (app.js:511, `replaceAll`), aber `s.state.replace(" ", "-")` (app.js:89) und
  `e.result.replace(" ", "-")` (historie.js:73) ersetzen nur das erste Leerzeichen.
- Die Historie baut den Schildkröten-Platzhalter von Hand nach (historie.js:121), statt `turtle()` zu nutzen.

### 4.3 Durchschnittsfortschritt doppelt
Identische Berechnung in `renderSummary` (app.js:578) und `renderJobs` (app.js:638–639), dazu die Liste
`["fehler", "übersprungen"]` doppelt neben `FINISHED_STATES`. → `avgProgress(tasks)`.

### 4.4 „Various Artists“-Schalter doppelt
`#bulk-va` (app.js:407–419) und `#album-va` (app.js:812, 831–844) merken sich den alten Wert, setzen `VA`,
sperren Felder und stellen beim Abwählen wieder her. → `vaToggle(checkbox, field, alsoDisable, onChange)`.

### 4.5 „Geändert“-Markierung und Zurücksetzen doppelt
Vorschau (`tagSnapshot`, `isChanged`, Zellen-Markierung, ↺-Button; app.js:311–314, 381–395) und Albumtabelle
(`trackCopy`, `trackChanged`, `mark`; app.js:741, 874–886) lösen dasselbe Problem getrennt.
→ ein Helfer `editableField(obj, key, {type})`, der Eingabefeld, `changed`-Klasse und Tooltip pflegt, plus
`isChanged(obj, keys)`.

### 4.6 Download mit Konfliktdialog doppelt
`#download-btn` (app.js:470–491) und `#album-cut` (app.js:1014–1042): Konflikte abfragen → Dialog → Entscheidungen
eintragen → „alles übersprungen?“ → Job anlegen → Bereich ausblenden, URL leeren.
→ `submitWithConflicts({ conflictsUrl, jobsUrl, body, entries, idOf })`.

Dabei auch: Das Frontend rekonstruiert die Titel-IDs des Servers (`${album.id}-${n:02}`, app.js:1027–1029). Das
koppelt Client und Server an ein Namensschema. Besser liefert der Konflikt-Endpunkt den Track-Index mit, oder
das Frontend schickt eigene IDs pro Track mit.

### 4.7 Fehleranzeige und Live-Updates
- `box.textContent = err.message; box.hidden = false` steht an vier Stellen (app.js:197–198, 236–237, 486–487,
  729–730) → `showError(box, err)` / `hideError(box)`.
- `runActivity` (app.js:107–125) und `connectJobs` (app.js:681–696) haben jeweils SSE plus Polling-Fallback.
  `EventSource` unterstützen alle aktuellen Browser – der Fallback ließe sich streichen oder in einen Helfer
  `subscribe(sseUrl, pollFn, onData)` legen.
- `button()` (app.js:493) existiert, wird aber für Album-Zeilen, „Jetzt fortsetzen“, Hinweis-Chips und die
  Historie nicht genutzt; dort wird jeweils `el("button")` + `addEventListener` von Hand gebaut. Da `el`
  Eigenschaften setzt, die es auf dem Knoten gibt, funktioniert auch schon `el("button", { onclick: … })`.

---

## 5. Frontend – Kapselung und Vereinfachung

### 5.1 `app.js` aufteilen
Mit 1045 Zeilen und globalem Zustand (`preview`, `album`, `folders`, `showArtistCol`, `albumArtistBeforeVa`,
`bulkArtistBeforeVa`, `dragging`, `lastPlaying`, `lastJobs`, `collapsedJobs` …) ist `app.js` schwer zu
überblicken. Die Abschnitte sind schon durch Kommentare getrennt und lassen sich fast 1:1 in ES-Module schneiden:
`common.js`, `settings.js`, `preview.js` (Vorschau + Sammelbearbeitung + Cover), `album.js` (Album-Editor +
Wellenform), `jobs.js` (Liste + Zusammenfassung + Bot-Hinweis). Zustand je Modul statt global.

### 5.2 Kleinigkeiten
- `let bitrate` (app.js:130, 140) wird gesetzt, aber nie gelesen → entfernen.
- Zahlenfelder der Einstellungen werden per fest verdrahteter Namensliste umgewandelt (app.js:185). Besser:
  alle `input[type=number]`/`select` mit numerischem Wert über `valueAsNumber` bzw. ein `data-number`-Attribut.
  Sonst muss die Liste bei jedem neuen Zahlenfeld mitgepflegt werden.
- `${n} ${n === 1 ? "Titel" : "Titel"}` (historie.js:91, 127) – beide Zweige gleich, also überflüssig.
- Die CSS-Farben für die Wellenform werden bei jedem `timeupdate` neu per `getComputedStyle` gelesen
  (app.js:921–924). Einmal lesen und bei Theme-Wechsel (`matchMedia(...).onchange`) aktualisieren reicht.

---

## Empfohlene Reihenfolge

1. **Kleine, risikoarme Schritte:** 1.2, 1.3, 1.6, 1.7, 1.8, 2.2, 3.5 und 5.2 – reines Zusammenziehen, durch die
   bestehenden Tests abgedeckt.
2. **Status-Konstanten (2.1)** und **Bildverarbeitung nach `covers.py` (1.5)** – beseitigen Namenskonflikt und
   Kreisimport.
3. **`common.js` (4.1, 4.2)** – behebt nebenbei die auseinandergelaufene Fehlerbehandlung in der Historie.
4. **Größere Umbauten:** `downloader.py` aufteilen (2.3) zusammen mit 1.1 und 1.4, `AlbumCache` (2.4) mit 3.3,
   Task-Methoden (2.5), `put_settings` (3.1), `app.js` in Module (5.1).
