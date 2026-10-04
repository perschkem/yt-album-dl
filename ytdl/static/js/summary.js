// Texte der Download-Liste ohne DOM: Status eines Titels und die Zusammenfassung über der Liste.

import { avgProgress, countDone, countStatus } from "./format.js";

/** Statustext eines Titels, bei Wartezeiten mit Countdown. */
export function taskStatus(t) {
  if (t.status === "neuer Versuch") return `neuer Versuch in ${t.retry_in} s`;
  if (t.status === "pausiert") return `pausiert · noch ${Math.ceil(t.retry_in / 60)} min`;
  return t.status;
}

/** Zeile über der Liste. Gezählt werden nur Downloads, die noch laufen – abgeschlossene zählen nicht mit,
 *  sonst stünde nach einem fertigen 10er-Album beim nächsten 12er-Album „10 von 22“. Läuft nichts mehr, zählt
 *  der zuletzt gestartete Download (steht oben in der Liste). Liefert null bei leerer Liste, sonst
 *  {state: running | paused | failed | done, icon, text, progress (nur running)}. */
export function summarize(jobs) {
  if (!jobs.length) return null;
  const active = jobs.filter((j) => countDone(j.tasks) < j.tasks.length);
  const tasks = (active.length ? active : [jobs[0]]).flatMap((j) => j.tasks);
  const done = countDone(tasks);
  const failed = countStatus(tasks, "fehler");
  const skipped = countStatus(tasks, "übersprungen");
  const running = tasks.length - done;
  const extras = [failed && `${failed} Fehler`, skipped && `${skipped} übersprungen`].filter(Boolean);

  const paused = tasks.filter((t) => t.status === "pausiert");
  if (paused.length) {
    // YouTube-Bot-Prüfung: Downloads ruhen, bis die Pause vorbei ist oder fortgesetzt wird
    const minutes = Math.ceil(Math.max(...paused.map((t) => t.retry_in)) / 60);
    return { state: "paused", icon: "⏸", text: `YouTube verlangt eine Bot-Bestätigung – Downloads pausieren noch ` +
      `ca. ${minutes} min (${done} von ${tasks.length} fertig)` };
  }
  if (active.length) {
    const prefix = active.length === 1 ? `${active[0].title}: ` : "";
    const text = [`${prefix}${done} von ${tasks.length} fertig`, `${running} ${running === 1 ? "läuft" : "laufen"}`,
      ...extras].join(" · ");
    return { state: "running", icon: "⏳", text, progress: avgProgress(tasks) };
  }
  if (failed) return { state: "failed", icon: "⚠", text: ["Alle Downloads abgeschlossen", ...extras].join(" · ") };
  return { state: "done", icon: "✓", text: ["Alle Downloads fertig", ...extras].join(" · ") };
}

/** Zähler im Kopf eines Downloads: „3/5 · 1 Fehler · MP3“. */
export function jobCounter(job) {
  return [`${job.done}/${job.total}`, job.failed && `${job.failed} Fehler`, job.skipped && `${job.skipped} übersprungen`,
    (job.audio_format || "").toUpperCase()].filter(Boolean).join(" · ");
}
