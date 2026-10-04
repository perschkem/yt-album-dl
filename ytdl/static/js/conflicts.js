// Konflikt-Dialog: Überschreiben / Überspringen / Beide behalten – und das Anlegen eines Jobs mit den Antworten.

import { api } from "./api.js";
import { $, el } from "./dom.js";
import { formatSize } from "./format.js";

const CONFLICT_CHOICES = [["keep_both", "Beide behalten (… (2))"], ["overwrite", "Überschreiben"], ["skip", "Überspringen"]];

/** Zeigt den Dialog für bereits vorhandene Dateien; liefert {id: Entscheidung} oder null bei Abbruch. */
export function resolveConflicts(conflicts) {
  if (!conflicts.length) return Promise.resolve({});
  const dialog = $("#conflict-dialog");
  const selects = conflicts.map((c) => {
    const select = el("select", { "aria-label": `Entscheidung für ${c.label}` },
      ...CONFLICT_CHOICES.map(([value, label]) => el("option", { value }, label)));
    return [c, select];
  });
  $("#conflict-list").replaceChildren(...selects.map(([c, select]) => el("div", { class: "conflict" },
    el("strong", {}, c.label), select,
    el("div", { class: "path" }, `${c.win_path} · ${formatSize(c.size)} · ${new Date(c.modified * 1000).toLocaleString("de-DE")}`))));
  dialog.querySelectorAll("[data-all]").forEach((b) => {
    b.onclick = () => selects.forEach(([, select]) => (select.value = b.dataset.all));
  });
  return new Promise((resolve) => {
    dialog.onclose = () => resolve(dialog.returnValue === "ok"
      ? Object.fromEntries(selects.map(([c, select]) => [c.id, select.value])) : null);
    dialog.returnValue = "";
    dialog.showModal();
  });
}

/** Fragt vorhandene Dateien ab, zeigt bei Bedarf den Konflikt-Dialog und legt den Job an – mit den
 *  Entscheidungen je Titel-ID, wie der Server sie geliefert hat. Liefert false bei Abbruch oder wenn alle
 *  `count` Titel übersprungen würden. `resolve` ist der Dialog (austauschbar für Tests). */
export async function submitWithConflicts(conflictsUrl, jobsUrl, body, count, resolve = resolveConflicts) {
  const decisions = await resolve(await api(conflictsUrl, body));
  if (decisions === null) return false;
  if (Object.values(decisions).filter((d) => d === "skip").length >= count) return false;
  await api(jobsUrl, { ...body, decisions });
  return true;
}
