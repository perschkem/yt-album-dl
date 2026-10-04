// Fortschritt: Balken mit Schildkröte, Schrittprotokoll eines Hintergrund-Vorgangs, Warte-Schildkröte.

import { api, subscribe } from "./api.js";
import { el, turtle } from "./dom.js";
import { cssName } from "./format.js";

export function showBusy(box, text) {
  box.hidden = !text;
  if (text) box.replaceChildren(turtle("pruefen", { size: 120, walking: true }), el("span", {}, text));
}

const STEP_ICONS = { "läuft": "", "fertig": "✓", "nichts gefunden": "✗", "übersprungen": "–", "fehler": "⚠" };

/** Unbestimmter Balken für Schritte ohne messbaren Fortschritt: die Schildkröte läuft hin und her.
 *  Die Schritte werden jede Sekunde neu gezeichnet (Sekundenzähler) – damit die Animation dabei nicht
 *  von vorn beginnt, richtet sich ihre Phase nach der Uhr (negativer animation-delay). */
const PATROL_SECONDS = 5, STRIPE_SECONDS = 0.8, WALK_SECONDS = 0.5;
function indeterminateBar() {
  const now = Date.now() / 1000;
  const phase = (period) => `-${(now % period).toFixed(3)}s`;
  return el("div", { class: "bar indeterminate" },
    el("div", { class: "fill", style: `animation-delay:${phase(STRIPE_SECONDS)}` }),
    el("div", { class: "runner", style: `animation-delay:${phase(PATROL_SECONDS)},${phase(WALK_SECONDS)}` }));
}

export function renderSteps(box, steps) {
  box.hidden = !steps.length;
  box.replaceChildren(...steps.map((s) => {
    const running = s.state === "läuft";
    const detail = [s.detail, running && s.elapsed >= 1 ? `${s.elapsed} s` : ""].filter(Boolean).join(" · ");
    return el("div", { class: `step ${cssName(s.state)}` },
      el("span", { class: "step-icon" }, STEP_ICONS[s.state] ?? ""),
      el("span", { class: "step-label" }, s.label),
      detail ? el("span", { class: "step-detail" }, detail) : null,
      running ? (s.progress != null ? progressBar(s.progress) : indeterminateBar()) : null);
  }));
}

/** Startet einen Hintergrund-Vorgang und zeigt dessen Schritte live in `box` (Server-Sent Events,
 *  Fallback: Abfrage); liefert das Ergebnis. */
export async function runActivity(path, body, box) {
  const { activity_id } = await api(path, body);
  const finish = (act) => {
    renderSteps(box, act.steps);
    if (act.status === "fertig") return { done: true, value: { ...act.result, steps: act.result.steps || act.steps } };
    if (act.status === "fehler") return { done: true, error: new Error(act.error) };
    return { done: false };
  };
  return new Promise((resolve, reject) => {
    const settle = (r) => (r.error ? reject(r.error) : resolve(r.value));
    const poll = async () => {
      try {
        while (true) {
          const r = finish(await api(`/api/activities/${activity_id}`));
          if (r.done) return settle(r);
          await new Promise((ok) => setTimeout(ok, 500));
        }
      } catch (err) { reject(err); }
    };
    // Bricht der Stream ab (z.B. Server neu gestartet), wird bis zum Ende abgefragt
    const source = subscribe(`/api/activities/${activity_id}/events`, (data) => {
      const r = finish(data);
      if (r.done) { source.close(); settle(r); }
    }, () => { source.close(); poll(); });
  });
}

export function progressBar(progress) {
  return el("div", { class: "bar" },
    el("div", { class: "fill", style: `width:${progress}%` }),
    el("div", { class: "runner", style: `left:${Math.min(97, Math.max(3, progress))}%` }));
}
