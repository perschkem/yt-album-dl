import { api, subscribe } from "./js/api.js";
import { $, button, el, emptyState, hideError, showError, turtle } from "./js/dom.js";
import { avgProgress, countDone, countStatus, cssName, formatSize, formatTime, isChanged, parseTime, primaryArtist,
  sameValue, snapshot } from "./js/format.js";

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

let preview = null; // { title, mode, items: [...] }

document.querySelectorAll("[data-turtle]").forEach((slot) => slot.append(turtle(slot.dataset.turtle, { size: 120 })));

function showBusy(box, text) {
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

function renderSteps(box, steps) {
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
async function runActivity(path, body, box) {
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

async function loadConfig() {
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

/** Hinweis + gesperrte Buttons, solange für den gewählten Modus kein Zielordner eingestellt ist. */
function updateFolderState() {
  const missing = [!folders.musik && "Musik", !folders.podcast && "Podcasts"].filter(Boolean);
  $("#folder-warning").hidden = !missing.length;
  $("#folder-warning-text").textContent = missing.length
    ? `Kein Zielordner für ${missing.join(" und ")} eingestellt – Herunterladen ist bis dahin gesperrt.` : "";
  const previewMode = preview?.mode || selectedMode();
  const download = $("#download-btn");
  download.disabled = !folders[previewMode];
  download.title = folders[previewMode] ? "" : "Erst unter ⚙ Einstellungen einen Ordner festlegen";
  const cut = $("#album-cut");
  cut.disabled = !folders.musik;
  cut.title = folders.musik ? "" : "Erst unter ⚙ Einstellungen einen Ordner für Musik festlegen";
}

document.querySelectorAll("input[name=mode]").forEach((r) => r.addEventListener("change", updateFolderState));

// ---------- Einstellungen ----------

const settingsDialog = $("#settings-dialog");

async function openSettings() {
  const s = await api("/api/settings");
  const form = $("#settings-form");
  $("#set-bitrate").replaceChildren(...s.bitrates.map((b) => el("option", { value: b }, `${b} kbit/s`)));
  $("#browser-list").replaceChildren(...s.browsers.map((b) => el("option", { value: b })));
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

function selectedMode() {
  return document.querySelector("input[name=mode]:checked").value;
}

function selectedFormat() {
  return document.querySelector("input[name=fmt]:checked")?.value || "";
}

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
    updateFolderState();
  } catch (err) {
    showError($("#probe-error"), err);
  } finally {
    showBusy($("#probe-busy"), "");
    btn.disabled = false;
    btn.textContent = "Prüfen";
  }
});

// ---------- Eigenes Cover per URL ----------

/** Cover-Feld: „Vorschaubild“ (Standard, schwarze Ränder werden entfernt) oder „Eigene URL“ mit Prüfung.
 *  Liefert {value(), clear(), setThumbnail(src, note)}. Bei eigener URL wird immer der Feldinhalt gesendet –
 *  die Prüfung ist nur Rückmeldung, der Server prüft beim Download selbst und nimmt sonst das Vorschaubild. */
function coverField(root) {
  const input = root.querySelector("input[type=url]");
  const crop = root.querySelector(".cover-crop");
  const img = root.querySelector(".cover-preview");
  const msg = root.querySelector(".cover-msg");
  const note = root.querySelector(".cover-thumb-note");
  const urlPart = root.querySelector(".cover-url-part");
  const modes = root.querySelectorAll(".cover-mode input");
  let thumbSrc = "", thumbNote = "";
  const mode = () => root.querySelector(".cover-mode input:checked").value;
  const show = (text, isError = false) => { msg.textContent = text; msg.classList.toggle("error", isError); };

  function showThumbnail() {
    img.hidden = !thumbSrc;
    if (thumbSrc) img.src = `/api/cover/thumbnail?src=${encodeURIComponent(thumbSrc)}`;
    note.textContent = thumbNote || "YouTube-Vorschaubild, schwarze Ränder werden entfernt.";
  }

  async function checkUrl() {
    const url = input.value.trim();
    img.hidden = true;
    if (!url) return show("");
    show("Prüfe Cover …");
    try {
      const info = await api("/api/cover/check", { url });
      if (input.value.trim() !== url || mode() !== "url") return; // inzwischen geändert
      img.src = url;
      img.hidden = false;
      show(`${info.width}×${info.height} px` + (info.square ? "" : " · nicht quadratisch"));
    } catch (err) {
      show(`${err.message} – es bleibt das YouTube-Vorschaubild`, true);
    }
  }

  function applyMode() {
    const isUrl = mode() === "url";
    urlPart.hidden = !isUrl;
    note.hidden = isUrl;
    if (isUrl) checkUrl(); else showThumbnail();
  }

  img.addEventListener("error", () => { if (mode() === "thumb") img.hidden = true; });
  modes.forEach((r) => r.addEventListener("change", applyMode));
  input.addEventListener("change", checkUrl);
  return {
    value: () => mode() === "url"
      ? { cover_url: input.value.trim(), cover_crop: crop.checked }
      : { cover_url: "", cover_crop: false },
    clear: () => {
      input.value = ""; crop.checked = false; show("");
      root.querySelector(".cover-mode input[value=thumb]").checked = true;
      applyMode();
    },
    setThumbnail: (src, text = "") => { thumbSrc = src || ""; thumbNote = text; if (mode() === "thumb") showThumbnail(); },
  };
}

const previewCover = coverField($("#preview-cover"));
const albumCover = coverField($("#album-cover"));

// ---------- Tags zurücksetzen ----------
const TAG_KEYS = ["artist", "title", "album", "album_artist", "track_no", "track_total", "year", "date"];
const tagsChanged = (item) => isChanged(item, item.orig, TAG_KEYS);

/** Eingabezelle für obj[key]: Zelle ist als „geändert“ markiert, solange der Wert von obj.orig[key] abweicht. */
function editableCell(obj, key, { type = "text", cls = "", onInput } = {}) {
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
function resetButton(obj, keys, onReset, cls) {
  const b = el("button", { type: "button", class: cls,
    title: obj.orig ? "Erkannte Werte wiederherstellen" : "Von Hand hinzugefügt" }, "↺");
  b.addEventListener("click", () => { Object.assign(obj, obj.orig); onReset(); });
  b.refresh = () => (b.disabled = !isChanged(obj, obj.orig, keys));
  b.refresh();
  return b;
}

/** Checkbox „Verschiedene Interpreten“: setzt das Feld auf „Various Artists“ und sperrt es (samt `alsoDisable`);
 *  beim Abwählen kommt der vorherige Wert zurück. onChange(aktueller Albuminterpret). */
function vaToggle(checkbox, field, alsoDisable = [], onChange = () => {}) {
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

/** „Automatisch nummerieren“: ausgewählte Titel in Listenreihenfolge 1…n, abgewählte ohne Nummer. */
function renumber() {
  if (!$("#bulk-autonum").checked) return;
  const selected = preview.items.filter((i) => i.selected);
  let n = 0;
  preview.items.forEach((i) => {
    i.track_no = i.selected ? ++n : null;
    i.track_total = i.selected ? selected.length : null;
  });
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
  $("#preview-count").textContent = `${preview.items.length} ${preview.items.length === 1 ? "Eintrag" : "Einträge"}`;

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

const VA = "Various Artists";

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

// ---------- Konflikt-Dialog: Überschreiben / Überspringen / Beide behalten ----------

const CONFLICT_CHOICES = [["keep_both", "Beide behalten (… (2))"], ["overwrite", "Überschreiben"], ["skip", "Überspringen"]];

/** Zeigt den Dialog für bereits vorhandene Dateien; liefert {id: Entscheidung} oder null bei Abbruch. */
function resolveConflicts(conflicts) {
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
 *  `count` Titel übersprungen würden. */
async function submitWithConflicts(conflictsUrl, jobsUrl, body, count) {
  const decisions = await resolveConflicts(await api(conflictsUrl, body));
  if (decisions === null) return false;
  if (Object.values(decisions).filter((d) => d === "skip").length >= count) return false;
  await api(jobsUrl, { ...body, decisions });
  return true;
}

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

const openPath = (path) => api("/api/open", { path });
const retry = (jobId, taskId = null) => api(`/api/jobs/${jobId}/retry`, { task_id: taskId });

function taskStatus(t) {
  if (t.status === "neuer Versuch") return `neuer Versuch in ${t.retry_in} s`;
  if (t.status === "pausiert") return `pausiert · noch ${Math.ceil(t.retry_in / 60)} min`;
  return t.status;
}

function progressBar(progress) {
  return el("div", { class: "bar" },
    el("div", { class: "fill", style: `width:${progress}%` }),
    el("div", { class: "runner", style: `left:${Math.min(97, Math.max(3, progress))}%` }));
}

function renderTask(job, t) {
  const actions = [];
  if (t.status === "fehler") actions.push(button("↻ Erneut versuchen", () => retry(job.id, t.id), { cls: "small-btn" }));
  return el("div", { class: `task ${cssName(t.status)}` },
    el("div", { class: "task-head" }, el("span", {}, t.label),
      el("span", { class: `status ${cssName(t.status)}` }, taskStatus(t))),
    progressBar(t.progress),
    t.detail ? el("div", { class: "detail" }, t.detail) : null,
    t.win_path ? el("div", { class: "path" }, t.win_path) : null,
    t.error ? el("div", { class: "err" }, t.error) : null,
    actions.length ? el("div", { class: "task-actions" }, ...actions) : null,
  );
}


/** Zeile über der Liste. Gezählt werden nur Downloads, die noch laufen – abgeschlossene zählen nicht mit,
 *  sonst stünde nach einem fertigen 10er-Album beim nächsten 12er-Album „10 von 22“. */
function renderSummary(jobs) {
  const box = $("#jobs-summary");
  box.hidden = !jobs.length;
  if (!jobs.length) return;
  const active = jobs.filter((j) => countDone(j.tasks) < j.tasks.length);
  // Läuft nichts mehr: Ergebnis des zuletzt gestarteten Downloads (steht oben in der Liste)
  const scope = active.length ? active : [jobs[0]];
  const tasks = scope.flatMap((j) => j.tasks);
  const done = countDone(tasks);
  const failed = countStatus(tasks, "fehler");
  const skipped = countStatus(tasks, "übersprungen");
  const running = tasks.length - done;
  const extras = [failed && `${failed} Fehler`, skipped && `${skipped} übersprungen`].filter(Boolean);
  let icon, text;
  if (active.length) {
    icon = "⏳";
    const prefix = active.length === 1 ? `${active[0].title}: ` : "";
    text = [`${prefix}${done} von ${tasks.length} fertig`, `${running} ${running === 1 ? "läuft" : "laufen"}`, ...extras].join(" · ");
  } else if (failed) {
    icon = "⚠";
    text = ["Alle Downloads abgeschlossen", ...extras].join(" · ");
  } else {
    icon = "✓";
    text = ["Alle Downloads fertig", ...extras].join(" · ");
  }
  const paused = tasks.filter((t) => t.status === "pausiert");
  if (paused.length) {
    // YouTube-Bot-Prüfung: Hinweis + Möglichkeit, nach dem Hinterlegen von Cookies sofort weiterzumachen
    const minutes = Math.ceil(Math.max(...paused.map((t) => t.retry_in)) / 60);
    box.className = "jobs-summary paused";
    const resume = button("Jetzt fortsetzen", () => api("/api/jobs/resume", {}), { cls: "small-btn" });
    const settings = el("button", { type: "button", class: "small-btn", onclick: openSettings },
      "⚙ YouTube-Anmeldung einrichten");
    box.replaceChildren(el("span", { class: "summary-icon" }, "⏸"),
      el("span", {}, `YouTube verlangt eine Bot-Bestätigung – Downloads pausieren noch ca. ${minutes} min ` +
        `(${done} von ${tasks.length} fertig)`), resume, settings);
    return;
  }
  box.className = `jobs-summary ${active.length ? "running" : failed ? "failed" : "done"}`;
  // replaceChildren filtert null nicht (würde als Text „null“ erscheinen) – deshalb bedingt anhängen
  box.replaceChildren(el("span", { class: "summary-icon" }, icon), el("span", {}, text));
  if (active.length) box.append(progressBar(avgProgress(tasks)));
}

// Eingeklappte Downloads merken – die Liste wird bei jedem Live-Update neu gezeichnet, und der Zustand
// soll auch ein Neuladen der Seite überstehen (nur im eigenen Browser).
const collapsedJobs = new Set((() => {
  try { return JSON.parse(localStorage.getItem("ytdl-collapsed") || "[]"); } catch { return []; }
})());
let lastJobs = [];

function saveCollapsed() {
  try { localStorage.setItem("ytdl-collapsed", JSON.stringify([...collapsedJobs])); } catch { /* egal */ }
}

function toggleJob(id) {
  if (collapsedJobs.has(id)) collapsedJobs.delete(id); else collapsedJobs.add(id);
  saveCollapsed();
  renderJobs(lastJobs);
}

$("#toggle-jobs").addEventListener("click", () => {
  const allCollapsed = lastJobs.every((j) => collapsedJobs.has(j.id));
  lastJobs.forEach((j) => (allCollapsed ? collapsedJobs.delete(j.id) : collapsedJobs.add(j.id)));
  saveCollapsed();
  renderJobs(lastJobs);
});

function renderJobs(jobs) {
  lastJobs = jobs;
  // Zustand nur für vorhandene Jobs behalten (z.B. nach „Liste leeren“)
  for (const id of collapsedJobs) if (!jobs.some((j) => j.id === id)) collapsedJobs.delete(id);
  renderSummary(jobs);
  $("#clear-jobs").hidden = !jobs.some((j) => j.done === j.total);
  $("#toggle-jobs").hidden = jobs.length < 2;
  $("#toggle-jobs").textContent = jobs.length && jobs.every((j) => collapsedJobs.has(j.id)) ? "Alle ausklappen" : "Alle einklappen";
  if (!jobs.length) {
    $("#jobs").replaceChildren(emptyState("Noch keine Downloads."));
    return;
  }
  $("#jobs").replaceChildren(...jobs.map((job) => {
    const head = [];
    // „Ordner öffnen“ nur einmal pro Job; bei einem einzelnen Titel wird die Datei im Explorer markiert
    const finished = job.tasks.filter((t) => t.path);
    if (job.folder) {
      const target = finished.length === 1 ? finished[0].path : job.folder;
      head.push(button("📂 Ordner öffnen", () => openPath(target), { title: "Im Explorer anzeigen" }));
    }
    if (job.failed) head.push(button(`↻ ${job.failed} fehlgeschlagene wiederholen`, () => retry(job.id), { cls: "small-btn" }));
    const counter = `${job.done}/${job.total}` + (job.failed ? ` · ${job.failed} Fehler` : "") +
      (job.skipped ? ` · ${job.skipped} übersprungen` : "") + ` · ${(job.audio_format || "").toUpperCase()}`;
    const collapsed = collapsedJobs.has(job.id);
    const title = el("h3", { title: collapsed ? "Ausklappen" : "Einklappen" },
      el("span", { class: "job-title" }, `${job.mode === "musik" ? "🎵" : "🎙️"} ${job.title}`),
      el("span", { class: "muted" }, counter));
    title.addEventListener("click", () => toggleJob(job.id));
    const running = job.done < job.total;
    const card = el("div", { class: `job${collapsed ? " collapsed" : ""}` }, title);
    if (collapsed) {
      // eingeklappt: nur Kopf, bei laufendem Download mit Gesamtbalken
      if (running) card.append(Object.assign(progressBar(avgProgress(job.tasks)), { className: "bar job-bar" }));
      return card;
    }
    if (head.length) card.append(el("div", { class: "task-actions job-actions" }, ...head));
    card.append(...job.tasks.map((t) => renderTask(job, t)));
    return card;
  }));
}

const clockTime = (ts) => new Date(ts * 1000).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });

/** Hinweis oben, wenn YouTube eine Bot-Prüfung verlangt hat – damit man merkt, dass gerade mit
 *  Anmeldung geladen wird bzw. warum Downloads pausieren. */
function renderAuthNotice(auth) {
  const box = $("#auth-notice");
  const show = auth && (auth.cookies_active || auth.recent_bot_check);
  box.hidden = !show;
  if (!show) return;
  const when = auth.last_bot_check ? clockTime(auth.last_bot_check) : "";
  let text;
  if (auth.cookies_active) {
    text = `🔑 YouTube hat${when ? ` um ${when}` : ""} eine Bot-Prüfung verlangt. Downloads laufen deshalb bis ` +
      `${clockTime(auth.cookies_until)} mit deiner YouTube-Anmeldung (Cookies), danach wieder ohne.`;
  } else if (auth.cookies_configured) {
    text = `⚠ YouTube hat${when ? ` um ${when}` : ""} eine Bot-Prüfung verlangt – auch mit Anmeldung. ` +
      "Downloads pausieren; später erneut versuchen oder die Cookies neu exportieren.";
  } else {
    text = `⚠ YouTube hat${when ? ` um ${when}` : ""} eine Bot-Prüfung verlangt. Ohne hinterlegte ` +
      "YouTube-Anmeldung pausieren Downloads, bis die Sperre vorbei ist (meist einige Stunden).";
  }
  $("#auth-notice-text").textContent = text;
  $("#auth-notice-open").hidden = auth.cookies_active;
}

$("#auth-notice-open").addEventListener("click", openSettings);

/** Live-Updates der Job-Liste (und des Anmeldestatus) per Server-Sent Events; EventSource verbindet sich
 *  bei Abbruch selbst neu. */
function connectJobs() {
  subscribe("/api/jobs/events", (data) => {
    renderJobs(data.jobs);
    renderAuthNotice(data.auth);
  });
}

$("#clear-jobs").addEventListener("click", async () => {
  await api("/api/jobs", null, "DELETE");
});

// ---------- Album in einem Video ----------

let album = null; // { id, duration, peaks, tracks: [{start, artist, title}] }
const audio = $("#album-audio");
const wave = $("#wave");

function albumBusy(busy, text = "Analysiere …") {
  document.querySelectorAll("#album button").forEach((b) => (b.disabled = busy));
  showBusy($("#album-busy"), busy ? text : "");
  if (busy) hideError($("#album-error"));
  else $("#album-steps").hidden = true;
}

const albumError = (err) => showError($("#album-error"), err);

function sortTracks() {
  album.tracks.sort((a, b) => a.start - b.start);
}

function trackEnd(i) {
  return i + 1 < album.tracks.length ? album.tracks[i + 1].start : album.duration;
}

const TRACK_KEYS = ["start", "artist", "title"];
const trackCopy = (t) => snapshot(t, TRACK_KEYS);

function setTracks(result, steps) {
  // Jede neue Erkennung (Analyse, Pausen, Trackliste, Scan) ist der neue Ausgangszustand für „Zurücksetzen“
  album.original.tracks = result.tracks.map(trackCopy);
  album.tracks = result.tracks.map((t) => ({ ...trackCopy(t), orig: trackCopy(t) }));
  album.source = result.source_label;
  $("#album-source").textContent = `Grenzen aus: ${result.source_label} · bitte kontrollieren`;
  if (steps) renderSteps($("#album-log-steps"), steps);
  renderAlbum();
}

$("#album-open").addEventListener("click", async () => {
  $("#preview").hidden = true;
  $("#album").hidden = false;
  $("#album-body").hidden = true;
  $("#album-source").textContent = "";
  albumBusy(true);
  try {
    const data = await runActivity("/api/album/analyze", { url: preview.url }, $("#album-steps"));
    album = { id: data.id, duration: data.duration, peaks: data.peaks, tracks: [], albumArtist: data.artist,
      original: { album: data.album, artist: data.artist, year: data.year || "", tracks: [] } };
    resetAlbumFields();
    albumCover.setThumbnail(data.thumbnail);
    renderHints(data.hints || []);
    audio.src = data.audio_url;
    $("#album-body").hidden = false;
    setTracks(data, data.steps);
  } catch (err) {
    albumError(err);
  } finally {
    albumBusy(false);
  }
});

function resetAlbumFields() {
  const o = album.original;
  albumCover.clear();
  showArtistCol = false;
  $("#album-va").checked = false;
  $("#album-artist").disabled = $("#album-apply").disabled = false;
  $("#album-name").value = o.album;
  $("#album-artist").value = o.artist;
  $("#album-year").value = o.year;
  $("#album-genre").value = "";
  album.albumArtist = o.artist;
}

$("#album-reset").addEventListener("click", () => {
  if (!confirm("Album-Felder, Titel und Grenzen auf das Ergebnis der Erkennung zurücksetzen?")) return;
  resetAlbumFields();
  album.tracks = album.original.tracks.map((t) => ({ ...trackCopy(t), orig: trackCopy(t) }));
  renderAlbum();
});

function renderHints(hints) {
  const box = $("#album-hints");
  box.hidden = !hints.length;
  box.replaceChildren("Weiterer Text im Bild (klicken = als Albuminterpret):",
    ...hints.map((h) => {
      return el("button", { type: "button", class: "chip", onclick: () => {
        if ($("#album-va").checked) return;
        $("#album-artist").value = h;
        setAlbumArtist(h);
      } }, h);
    }));
}

let showArtistCol = false;

/** Neuer Albuminterpret: Titel, die noch den alten Interpreten hatten, ziehen mit; abweichende bleiben. */
function setAlbumArtist(next) {
  const old = album.albumArtist;
  album.tracks.forEach((t) => { if (!t.artist || t.artist === old) t.artist = next; });
  album.albumArtist = next;
  renderAlbum();
}

$("#album-artist").addEventListener("change", () => setAlbumArtist($("#album-artist").value.trim()));

$("#album-apply").addEventListener("click", () => {
  const artist = $("#album-artist").value.trim();
  album.tracks.forEach((t) => (t.artist = artist));
  album.albumArtist = artist;
  renderAlbum();
});

// Interpreten der Titel bleiben bei „Verschiedene Interpreten“ einzeln erhalten
vaToggle($("#album-va"), $("#album-artist"), [$("#album-apply")], (artist) => {
  album.albumArtist = artist;
  renderAlbum();
});

$("#album-artist-col").addEventListener("click", () => {
  showArtistCol = !showArtistCol;
  renderAlbum();
});

function updateArtistColumn() {
  const va = $("#album-va").checked;
  const uniform = album.tracks.every((t) => t.artist === album.albumArtist);
  const hide = !va && !showArtistCol && uniform;
  $("#album-table").classList.toggle("hide-artist", hide);
  const toggle = $("#album-artist-col");
  toggle.hidden = va || !uniform;
  toggle.textContent = showArtistCol ? "Interpret-Spalte ausblenden" : "Interpret pro Titel bearbeiten";
}

function renderAlbum() {
  sortTracks();
  updateArtistColumn();
  const playing = currentTrackIndex();
  $("#album-tracks").replaceChildren(...album.tracks.map((t, i) => {
    const start = el("input", { value: formatTime(t.start, { tenths: true }), onchange: () => {
      const v = parseTime(start.value);
      if (v != null && v >= 0 && v < album.duration) t.start = v;
      renderAlbum();
    } });
    const startCell = el("td", { class: "time" }, start);
    startCell.classList.toggle("changed", !!t.orig && !sameValue(t.start, t.orig.start));
    const reset = resetButton(t, TRACK_KEYS, renderAlbum, "secondary");
    const action = (label, title, onclick) => el("button", { type: "button", class: "secondary", title, onclick }, label);
    return el("tr", { class: i === playing ? "playing" : "" },
      el("td", { class: "dur" }, String(i + 1)),
      startCell,
      el("td", { class: "dur" }, formatTime(trackEnd(i) - t.start)),
      editableCell(t, "artist", { onInput: reset.refresh }), editableCell(t, "title", { onInput: reset.refresh }),
      el("td", { class: "actions" },
        action("▶", "Ab Start abspielen", () => { audio.currentTime = t.start; audio.play(); }),
        action("⇤ hier", "Start = aktuelle Abspielposition", () => { t.start = audio.currentTime; renderAlbum(); }),
        reset,
        action("✕", "Grenze entfernen (mit vorherigem Titel zusammenfassen)", () => {
          album.tracks.splice(i, 1);
          renderAlbum();
        })));
  }));
  drawWave();
}

function currentTrackIndex() {
  if (!album) return -1;
  let idx = -1;
  album.tracks.forEach((t, i) => { if (audio.currentTime >= t.start) idx = i; });
  return idx;
}

function drawWave() {
  if (!album) return;
  const dpr = window.devicePixelRatio || 1;
  const w = wave.clientWidth, h = wave.clientHeight;
  wave.width = w * dpr; wave.height = h * dpr;
  const ctx = wave.getContext("2d");
  ctx.scale(dpr, dpr);
  const { accent, muted, text } = waveColors();

  ctx.fillStyle = muted;
  const n = album.peaks.length;
  for (let x = 0; x < w; x++) {
    const v = album.peaks[Math.floor((x / w) * n)] || 0;
    const bar = Math.max(1, v * (h - 22));
    ctx.fillRect(x, (h + 14 - bar) / 2, 1, bar);
  }
  ctx.font = "11px system-ui, sans-serif";
  album.tracks.forEach((t, i) => {
    const x = (t.start / album.duration) * w;
    ctx.fillStyle = accent;
    ctx.fillRect(x - 1, 0, 2, h);
    ctx.fillText(String(i + 1), x + 3, 11);
  });
  const px = (audio.currentTime / album.duration) * w;
  ctx.fillStyle = text;
  ctx.fillRect(px - 0.5, 0, 1, h);
}

// Farben aus dem Theme – einmal lesen und erst bei einem Wechsel hell/dunkel neu (drawWave läuft bei jedem timeupdate)
let colors = null;
function waveColors() {
  if (!colors) {
    const css = getComputedStyle(document.documentElement);
    const v = (name) => css.getPropertyValue(name).trim();
    colors = { accent: v("--frame"), muted: v("--muted"), text: v("--text") };
  }
  return colors;
}
window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => { colors = null; drawWave(); });

let dragging = null;
function waveTime(event) {
  const rect = wave.getBoundingClientRect();
  return Math.min(album.duration, Math.max(0, ((event.clientX - rect.left) / rect.width) * album.duration));
}
wave.addEventListener("pointerdown", (event) => {
  if (!album) return;
  const rect = wave.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const hit = album.tracks.findIndex((t, i) => i > 0 && Math.abs((t.start / album.duration) * rect.width - x) < 6);
  if (hit > 0) {
    dragging = album.tracks[hit];
    wave.setPointerCapture(event.pointerId);
  } else {
    audio.currentTime = waveTime(event);
    drawWave();
  }
});
wave.addEventListener("pointermove", (event) => {
  if (!dragging) return;
  dragging.start = waveTime(event);
  drawWave();
});
wave.addEventListener("pointerup", () => {
  if (!dragging) return;
  audio.currentTime = Math.max(0, dragging.start - 3);
  dragging = null;
  renderAlbum();
});

let lastPlaying = -1;
audio.addEventListener("timeupdate", () => {
  drawWave();
  const idx = currentTrackIndex();
  if (idx !== lastPlaying) {
    lastPlaying = idx;
    document.querySelectorAll("#album-tracks tr").forEach((tr, i) => tr.classList.toggle("playing", i === idx));
  }
});
window.addEventListener("resize", drawWave);

$("#album-add").addEventListener("click", () => {
  const artist = $("#album-va").checked ? "" : $("#album-artist").value;
  album.tracks.push({ start: audio.currentTime, artist, title: "" });
  renderAlbum();
});

async function albumAction(path, body) {
  albumBusy(true);
  const box = $("#album-steps");
  box.scrollIntoView({ block: "nearest", behavior: "smooth" });
  try {
    const result = await runActivity(`/api/album/${album.id}/${path}`,
      { ...body, artist: $("#album-artist").value }, box);
    setTracks(result, result.steps);
  } catch (err) {
    albumError(err);
  } finally {
    albumBusy(false);
  }
}

$("#det-run").addEventListener("click", () => {
  const count = $("#det-count").value ? Number($("#det-count").value) : null;
  albumAction("detect", { count, min_pause: Number($("#det-pause").value), sensitivity: Number($("#det-sens").value) });
});
$("#det-text-run").addEventListener("click", () => albumAction("text", { text: $("#det-text").value }));
$("#det-scan").addEventListener("click", () => albumAction("scan", {}));

$("#album-cut").addEventListener("click", async () => {
  albumBusy(true, "Prüfe, ob schon etwas da ist …");
  try {
    sortTracks();
    const body = {
      album: $("#album-name").value, album_artist: $("#album-artist").value,
      year: $("#album-year").value, genre: $("#album-genre").value,
      audio_format: selectedFormat(), ...albumCover.value(), boundary_source: album.source || "",
      tracks: album.tracks.map(({ orig, ...t }) => t),
    };
    const base = `/api/album/${album.id}`;
    if (!(await submitWithConflicts(`${base}/conflicts`, `${base}/jobs`, body, album.tracks.length))) return;
    audio.pause();
    $("#album").hidden = true;
    $("#url").value = "";
  } catch (err) {
    albumError(err);
  } finally {
    albumBusy(false);
  }
});

loadConfig();
connectJobs();
