// Texte der Download-Liste ohne DOM: Status eines Titels und die Zusammenfassung über der Liste.

import { avgProgress, countDone, countStatus } from "./format.js";
import { t } from "./i18n.js";

/** Statustext eines Titels, bei Wartezeiten mit Countdown. */
export function taskStatus(task) {
  const label = t(`status.${task.status}`);
  if (task.status === "retrying") return t("summary.retry_in", { label, seconds: task.retry_in });
  if (task.status === "paused") return t("summary.paused_for", { label, minutes: Math.ceil(task.retry_in / 60) });
  return label;
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
  const failed = countStatus(tasks, "failed");
  const skipped = countStatus(tasks, "skipped");
  const running = tasks.length - done;
  const extras = counts(failed, skipped);

  const paused = tasks.filter((task) => task.status === "paused");
  if (paused.length) {
    // YouTube-Bot-Prüfung: Downloads ruhen, bis die Pause vorbei ist oder fortgesetzt wird
    const minutes = Math.ceil(Math.max(...paused.map((task) => task.retry_in)) / 60);
    return { state: "paused", icon: "⏸", text: t("summary.paused", { minutes, done, total: tasks.length }) };
  }
  if (active.length) {
    const prefix = active.length === 1 ? `${active[0].title}: ` : "";
    const text = [prefix + t("summary.done_of", { done, total: tasks.length }), t("summary.running", { count: running }),
      ...extras].join(" · ");
    return { state: "running", icon: "⏳", text, progress: avgProgress(tasks) };
  }
  if (failed) return { state: "failed", icon: "⚠", text: [t("summary.all_finished"), ...extras].join(" · ") };
  return { state: "done", icon: "✓", text: [t("summary.all_done"), ...extras].join(" · ") };
}

/** Zähler im Kopf eines Downloads: „3/5 · 1 Fehler · MP3“. */
export function jobCounter(job) {
  return [`${job.done}/${job.total}`, ...counts(job.failed, job.skipped), (job.audio_format || "").toUpperCase()]
    .filter(Boolean).join(" · ");
}

/** „1 Fehler“, „2 übersprungen“ – nur, was vorkommt. */
function counts(failed, skipped) {
  return [failed && t("summary.failed_count", { count: failed }), skipped && t("summary.skipped_count", { count: skipped })]
    .filter(Boolean);
}
