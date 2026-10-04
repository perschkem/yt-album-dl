// Konfiguration vom Server, Zielordner-Hinweis und die Auswahl Modus/Format im Formular.

import { api } from "./api.js";
import { $ } from "./dom.js";

export async function loadConfig() {
  const cfg = await api("/api/config");
  folders = { musik: cfg.musik_dir, podcast: cfg.podcast_dir };
  document.querySelector(`input[name=fmt][value=${cfg.audio_format}]`).checked = true;
  const show = (dir) => dir || "nicht eingestellt";
  $("#dirs").textContent = `Musik: ${show(cfg.musik_dir)} · Podcasts: ${show(cfg.podcast_dir)} · ` +
    `${cfg.parallel_downloads} Downloads gleichzeitig`;
  updateFolderState();
  $("#ffmpeg-warning").hidden = cfg.ffmpeg;
}

let folders = { musik: "", podcast: "" };
let previewMode = null; // Modus der angezeigten Vorschau; ohne Vorschau gilt die Auswahl im Formular

/** Nach dem Prüfen: Herunterladen hängt vom Modus der Vorschau ab, nicht von der aktuellen Auswahl. */
export function setPreviewMode(mode) {
  previewMode = mode;
  updateFolderState();
}

/** Hinweis + gesperrte Buttons, solange für den gewählten Modus kein Zielordner eingestellt ist. */
function updateFolderState() {
  const missing = [!folders.musik && "Musik", !folders.podcast && "Podcasts"].filter(Boolean);
  $("#folder-warning").hidden = !missing.length;
  $("#folder-warning-text").textContent = missing.length
    ? `Kein Zielordner für ${missing.join(" und ")} eingestellt – Herunterladen ist bis dahin gesperrt.` : "";
  const mode = previewMode || selectedMode();
  const download = $("#download-btn");
  download.disabled = !folders[mode];
  download.title = folders[mode] ? "" : "Erst unter ⚙ Einstellungen einen Ordner festlegen";
  const cut = $("#album-cut");
  cut.disabled = !folders.musik;
  cut.title = folders.musik ? "" : "Erst unter ⚙ Einstellungen einen Ordner für Musik festlegen";
}

document.querySelectorAll("input[name=mode]").forEach((r) => r.addEventListener("change", updateFolderState));

export function selectedMode() {
  return document.querySelector("input[name=mode]:checked").value;
}

export function selectedFormat() {
  return document.querySelector("input[name=fmt]:checked")?.value || "";
}
