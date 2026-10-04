// Konfiguration vom Server, Zielordner-Hinweis und die Auswahl Modus/Format im Formular.

import { api } from "./api.js";
import { $ } from "./dom.js";
import { t } from "./i18n.js";

export async function loadConfig() {
  const cfg = await api("/api/config");
  folders = { musik: cfg.musik_dir, podcast: cfg.podcast_dir };
  document.querySelector(`input[name=fmt][value=${cfg.audio_format}]`).checked = true;
  const show = (dir) => dir || t("dirs.not_set");
  $("#dirs").textContent = t("dirs.summary", { music: show(cfg.musik_dir), podcasts: show(cfg.podcast_dir),
    count: cfg.parallel_downloads });
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
  const missing = ["musik", "podcast"].filter((m) => !folders[m]).map((m) => t(`folders.name_${m}`));
  $("#folder-warning").hidden = !missing.length;
  $("#folder-warning-text").textContent = missing.length
    ? t("folders.missing", { names: missing.join(t("folders.and")) }) : "";
  const mode = previewMode || selectedMode();
  const download = $("#download-btn");
  download.disabled = !folders[mode];
  download.title = folders[mode] ? "" : t("folders.set_first");
  const cut = $("#album-cut");
  cut.disabled = !folders.musik;
  cut.title = folders.musik ? "" : t("folders.set_music_first");
}

document.querySelectorAll("input[name=mode]").forEach((r) => r.addEventListener("change", updateFolderState));

export function selectedMode() {
  return document.querySelector("input[name=mode]:checked").value;
}

export function selectedFormat() {
  return document.querySelector("input[name=fmt]:checked")?.value || "";
}
