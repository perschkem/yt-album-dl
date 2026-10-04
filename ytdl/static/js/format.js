// Formatieren und kleine Rechnungen ohne DOM – von beiden Seiten genutzt, mit node --test getestet.

/** Sekunden → „m:ss“ bzw. „h:mm:ss“; tenths = mit Zehntelsekunden („m:ss.s“, für Schnittpunkte). */
export function formatTime(sec, { tenths = false } = {}) {
  let total = Math.max(0, sec || 0);
  if (!tenths) total = Math.round(total);
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  const ss = tenths ? s.toFixed(1).padStart(4, "0") : String(s).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/** „1:02:03.5“, „4:12“, „75“ oder „4,5“ → Sekunden; null bei ungültiger Eingabe. */
export function parseTime(text) {
  const parts = text.trim().replace(",", ".").split(":").map((p) => (p.trim() === "" ? NaN : Number(p)));
  if (parts.some(Number.isNaN)) return null;
  return parts.reduce((acc, v) => acc * 60 + v, 0);
}

/** Dateigröße für die Anzeige; leer, wenn unbekannt. */
export function formatSize(bytes) {
  if (!bytes) return "";
  return bytes >= 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Status-Text → CSS-Klasse („neuer Versuch“ → „neuer-Versuch“). */
export const cssName = (status) => String(status).replaceAll(" ", "-");

export const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

// ---------- Titel einer Download-Liste ----------

export const FINISHED_STATES = ["fertig", "fehler", "übersprungen"];
export const isFinished = (task) => FINISHED_STATES.includes(task.status);
export const countDone = (tasks) => tasks.filter(isFinished).length;
export const countStatus = (tasks, status) => tasks.filter((t) => t.status === status).length;

/** Durchschnittlicher Fortschritt; Fehler und Übersprungenes zählen als abgeschlossen (100 %). */
export function avgProgress(tasks) {
  if (!tasks.length) return 0;
  const sum = tasks.reduce((acc, t) => acc + (t.status === "fehler" || t.status === "übersprungen" ? 100 : t.progress), 0);
  return sum / tasks.length;
}

// ---------- Geänderte Werte (Vorschau und Albumtabelle) ----------

/** Gleich, wie die Eingabefelder es sehen (3 und "3", null und "" sind gleich). */
export const sameValue = (a, b) => String(a ?? "") === String(b ?? "");

/** Kopie der Felder `keys` – der Ausgangszustand für „Zurücksetzen“. */
export const snapshot = (obj, keys) => Object.fromEntries(keys.map((k) => [k, obj[k] ?? null]));

/** Wurde eins der Felder gegenüber `orig` geändert? Ohne `orig` (von Hand hinzugefügt) nie. */
export const isChanged = (obj, orig, keys) => !!orig && keys.some((k) => !sameValue(obj[k], orig[k]));

/** Hauptinterpret wie im Backend: „A feat. B“ / „A, B“ → „A“. */
export const primaryArtist = (artist) => artist.split(/ feat\. |, /)[0];
