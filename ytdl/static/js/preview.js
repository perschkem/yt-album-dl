// Prüfen einer URL und die Vorschau: Tags bearbeiten, Sammelbearbeitung, Cover, Herunterladen.

import { runActivity, showBusy } from "./progress.js";
import { selectedFormat, selectedMode, setPreviewMode } from "./config.js";
import { submitWithConflicts } from "./conflicts.js";
import { coverField } from "./cover.js";
import { $, el, hideError, showError } from "./dom.js";
import { editableCell, resetButton, vaToggle } from "./editing.js";
import { isChanged, numberSelected, plural, primaryArtist, snapshot } from "./format.js";

const COLUMNS = {
  musik: [
    { key: "track_no", label: "Nr.", cls: "num", type: "number" },
    { key: "artist", label: "Interpret" },
    { key: "title", label: "Titel" },
    { key: "album", label: "Album" },
    { key: "year", label: "Jahr", cls: "num" },
  ],
  podcast: [
    { key: "artist", label: "Kanal" },
    { key: "date", label: "Datum", cls: "date" },
    { key: "title", label: "Titel" },
  ],
};

const TAG_KEYS = ["artist", "title", "album", "album_artist", "track_no", "track_total", "year", "date"];
const tagsChanged = (item) => isChanged(item, item.orig, TAG_KEYS);

let preview = null; // { title, mode, url, items: [...] }
const previewCover = coverField($("#preview-cover"));

/** URL der zuletzt geprüften Vorschau (für die Album-Analyse). */
export const previewUrl = () => preview?.url || "";

$("#probe-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const btn = $("#probe-btn");
  const mode = selectedMode();
  btn.disabled = true;
  btn.textContent = "Prüfe …";
  hideError($("#probe-error"));
  $("#preview").hidden = true;
  showBusy($("#probe-busy"), "Lade Infos …");
  try {
    const data = await runActivity("/api/probe", { url: $("#url").value, mode }, $("#probe-steps"));
    $("#probe-steps").hidden = true;
    previewCover.clear();
    preview = { title: data.title, mode, url: $("#url").value.trim(),
      items: data.items.map((i) => ({ ...i, selected: !i.already, orig: snapshot(i, TAG_KEYS) })) };
    $("#album").hidden = true;
    $("#album-hint").hidden = !data.album_video;
    renderPreview(data.is_playlist);
    const first = preview.items[0];
    previewCover.setThumbnail(first?.thumbnail, preview.items.length > 1
      ? "Jeder Titel bekommt sein eigenes YouTube-Vorschaubild (schwarze Ränder werden entfernt) – Vorschau: erster Titel."
      : "");
    setPreviewMode(mode);
  } catch (err) {
    showError($("#probe-error"), err);
  } finally {
    showBusy($("#probe-busy"), "");
    btn.disabled = false;
    btn.textContent = "Prüfen";
  }
});

/** „Automatisch nummerieren“: ausgewählte Titel in Listenreihenfolge 1…n, abgewählte ohne Nummer. */
function renumber() {
  if ($("#bulk-autonum").checked) numberSelected(preview.items);
}

$("#bulk-autonum").addEventListener("change", () => {
  if ($("#bulk-autonum").checked) renumber();
  else preview.items.forEach((i) => { i.track_no = i.orig.track_no; i.track_total = i.orig.track_total; });
  renderRows();
});

function fillBulk() {
  const first = preview.items[0];
  $("#bulk-autonum").checked = preview.items.some((i) => i.track_no); // Album erkannt → schon nummeriert
  $("#bulk-album").value = first.album || "";
  $("#bulk-album-artist").value = first.album ? first.album_artist : "";
  $("#bulk-year").value = first.album ? first.year : "";
  $("#bulk-va").checked = $("#bulk-same-artist").checked = false;
  $("#bulk-album-artist").disabled = $("#bulk-same-artist").disabled = false;
}

$("#preview-reset").addEventListener("click", () => {
  if (!preview.items.some(tagsChanged) || !confirm("Alle Tags auf die erkannten Werte zurücksetzen?")) return;
  preview.items.forEach((i) => Object.assign(i, i.orig));
  if (!$("#bulk").hidden) fillBulk();
  previewCover.clear();
  renderRows();
});

function renderPreview(isPlaylist) {
  const cols = COLUMNS[preview.mode];
  $("#preview").hidden = false;
  $("#preview-title").textContent = isPlaylist ? preview.title : (preview.mode === "musik" ? "Titel" : "Video");
  $("#preview-count").textContent = plural(preview.items.length, "Eintrag", "Einträge");

  const bulk = preview.mode === "musik" && preview.items.length > 1;
  $("#bulk").hidden = !bulk;
  if (bulk) fillBulk();

  const allBox = el("input", { type: "checkbox", title: "Alle auswählen",
    checked: preview.items.every((i) => i.selected) });
  allBox.addEventListener("change", () => {
    preview.items.forEach((i) => (i.selected = allBox.checked));
    renumber();
    renderRows();
  });
  $("#preview-head").replaceChildren(
    el("th", {}, allBox), ...cols.map((c) => el("th", {}, c.label)), el("th", {}, "Original"), el("th", {}));
  renderRows();
}

function renderRows() {
  const cols = COLUMNS[preview.mode];
  $("#preview-body").replaceChildren(...preview.items.map((item) => {
    const box = el("input", { type: "checkbox", checked: item.selected });
    box.addEventListener("change", () => {
      item.selected = box.checked;
      if ($("#bulk-autonum").checked) { renumber(); renderRows(); }
    });
    const reset = resetButton(item, TAG_KEYS, renderRows, "small-btn");
    const cells = cols.map((c) => editableCell(item, c.key, { type: c.type, cls: c.cls, onInput: reset.refresh }));
    const orig = el("td", { class: "orig" }, item.source_title,
      item.already ? el("div", {}, el("span", { class: "badge" }, "bereits geladen")) : null);
    return el("tr", { class: item.already ? "already" : "" }, el("td", {}, box), ...cells, orig,
      el("td", { class: "actions" }, reset));
  }));
}

vaToggle($("#bulk-va"), $("#bulk-album-artist"), [$("#bulk-same-artist")]);

$("#bulk-apply").addEventListener("click", () => {
  const album = $("#bulk-album").value.trim();
  const albumArtist = $("#bulk-album-artist").value.trim();
  const year = $("#bulk-year").value.trim();
  const sameArtist = $("#bulk-same-artist").checked && albumArtist;
  preview.items.forEach((item) => {
    if (sameArtist) item.artist = albumArtist;
    item.album = album;
    item.album_artist = album ? (albumArtist || item.album_artist) : primaryArtist(item.artist);
    if (year) item.year = year;
  });
  // Mit Album → nummerieren; ohne Album sind es Singles ohne Tracknummer
  $("#bulk-autonum").checked = !!album;
  if (album) renumber();
  else preview.items.forEach((i) => { i.track_no = null; i.track_total = null; });
  renderRows();
});

$("#download-btn").addEventListener("click", async () => {
  const cover = previewCover.value();
  const items = preview.items.filter((i) => i.selected).map(({ selected, already, orig, ...rest }) => ({ ...rest, ...cover }));
  if (!items.length) return;
  const btn = $("#download-btn");
  btn.disabled = true;
  try {
    const body = { title: preview.title || items[0].title, mode: preview.mode, audio_format: selectedFormat(), items };
    if (!(await submitWithConflicts("/api/conflicts", "/api/jobs", body, items.length))) return;
    $("#preview").hidden = true;
    $("#url").value = "";
  } catch (err) {
    showError($("#probe-error"), err);
  } finally {
    btn.disabled = false;
  }
});
