// Einstellungsdialog (wird in .env gespeichert).

import { api } from "./api.js";
import { loadConfig } from "./config.js";
import { $, el, hideError, showError } from "./dom.js";
import { language } from "./i18n.js";

const settingsDialog = $("#settings-dialog");

export async function openSettings() {
  const s = await api("/api/settings");
  const form = $("#settings-form");
  $("#set-bitrate").replaceChildren(...s.bitrates.map((b) => el("option", { value: b }, `${b} kbit/s`)));
  $("#browser-list").replaceChildren(...s.browsers.map((b) => el("option", { value: b })));
  // Sprachnamen in der jeweils eigenen Sprache („Deutsch“, „English“)
  $("#set-language").replaceChildren(...Object.entries(s.languages).map(([code, name]) => el("option", { value: code }, name)));
  for (const [name, [min, max]] of Object.entries(s.limits)) Object.assign(form.elements[name], { min, max });
  for (const [name, value] of Object.entries(s)) {
    if (form.elements[name]) form.elements[name].value = value;
  }
  form.querySelectorAll(".field-error").forEach((p) => (p.textContent = ""));
  hideError($("#settings-error"));
  settingsDialog.showModal();
}

$("#open-settings").addEventListener("click", openSettings);
$("#folder-warning-open").addEventListener("click", openSettings);
$("#settings-cancel").addEventListener("click", () => settingsDialog.close());

$("#settings-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const body = Object.fromEntries(new FormData(form));
  // Zahlenfelder (type=number bzw. data-number) als Zahl senden
  for (const field of form.elements) {
    if (field.name && (field.type === "number" || "number" in field.dataset)) body[field.name] = Number(body[field.name]);
  }
  form.querySelectorAll(".field-error").forEach((p) => (p.textContent = ""));
  $("#settings-save").disabled = true;
  try {
    await api("/api/settings", body, "PUT");
    // Neue Sprache: Seite neu laden, damit alle Texte (auch die festen im HTML) neu übersetzt werden
    if (body.language && body.language !== language()) return location.reload();
    settingsDialog.close();
    await loadConfig();
  } catch (err) {
    for (const [field, message] of Object.entries(err.fields || {})) {
      const slot = form.querySelector(`.field-error[data-for=${field}]`);
      if (slot) slot.textContent = message;
    }
    showError($("#settings-error"), err);
  } finally {
    $("#settings-save").disabled = false;
  }
});
