// Bearbeitbare Tabellen (Vorschau und Album): Eingabezellen mit „geändert“-Markierung, Zurücksetzen, Sampler.

import { el } from "./dom.js";
import { isChanged, sameValue } from "./format.js";

export const VA = "Various Artists";

/** Eingabezelle für obj[key]: Zelle ist als „geändert“ markiert, solange der Wert von obj.orig[key] abweicht. */
export function editableCell(obj, key, { type = "text", cls = "", onInput } = {}) {
  const input = el("input", { type, value: obj[key] ?? "", title: obj[key] ?? "" });
  const td = el("td", { class: cls }, input);
  const mark = () => td.classList.toggle("changed", !!obj.orig && !sameValue(obj[key], obj.orig[key]));
  input.addEventListener("input", () => {
    obj[key] = type === "number" ? (input.value ? Number(input.value) : null) : input.value;
    input.title = input.value; // voller Text als Tooltip, falls das Feld zu schmal ist
    mark();
    onInput?.();
  });
  mark();
  return td;
}

/** ↺-Button: stellt obj.orig wieder her; refresh() sperrt ihn, solange nichts geändert ist. */
export function resetButton(obj, keys, onReset, cls) {
  const b = el("button", { type: "button", class: cls,
    title: obj.orig ? "Erkannte Werte wiederherstellen" : "Von Hand hinzugefügt" }, "↺");
  b.addEventListener("click", () => { Object.assign(obj, obj.orig); onReset(); });
  b.refresh = () => (b.disabled = !isChanged(obj, obj.orig, keys));
  b.refresh();
  return b;
}

/** Checkbox „Verschiedene Interpreten“: setzt das Feld auf „Various Artists“ und sperrt es (samt `alsoDisable`);
 *  beim Abwählen kommt der vorherige Wert zurück. onChange(aktueller Albuminterpret). */
export function vaToggle(checkbox, field, alsoDisable = [], onChange = () => {}) {
  let before = "";
  checkbox.addEventListener("change", () => {
    const on = checkbox.checked;
    if (on) before = field.value;
    field.value = on ? VA : before;
    field.disabled = on;
    for (const other of alsoDisable) {
      other.disabled = on;
      if (on && other.type === "checkbox") other.checked = false;
    }
    onChange(field.value);
  });
}
