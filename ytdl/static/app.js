const $ = (sel) => document.querySelector(sel);

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
    { key: "date", label: "Datum", cls: "num" },
    { key: "title", label: "Titel" },
  ],
};

let preview = null; // { title, mode, items: [...] }

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k in node) node[k] = v;
    else node.setAttribute(k, v);
  }
  node.append(...children.filter((c) => c != null));
  return node;
}

async function api(path, body, method) {
  const res = await fetch(path, body || method ? {
    method: method || "POST", headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  } : undefined);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Fehler ${res.status}`);
  return data;
}

// ---------- Schildkröten ----------
// Fertige Bilder je Situation (DESIGN.md). Fehlende kommen nach und nach – bis dahin der Pixel-Platzhalter.
const TURTLES = {
  pruefen: { src: "img/turtles/pruefen.webp", round: true },
};
const TURTLE_PLACEHOLDER = "img/turtles/platzhalter.svg";

function turtle(situation, { size = 64, walking = false, alt = "" } = {}) {
  const known = TURTLES[situation];
  const img = el("img", { src: known ? known.src : TURTLE_PLACEHOLDER, alt, width: size,
    height: known ? size : Math.round(size * 9 / 16), class: "turtle" });
  if (known?.round) img.classList.add("round");
  if (walking) img.classList.add("walking");
  return img;
}

document.querySelectorAll("[data-turtle]").forEach((slot) => slot.append(turtle(slot.dataset.turtle, { size: 72 })));

function showBusy(box, text) {
  box.hidden = !text;
  if (text) box.replaceChildren(turtle("pruefen", { size: 64, walking: true }), el("span", {}, text));
}

const STEP_ICONS = { "läuft": "", "fertig": "✓", "nichts gefunden": "✗", "übersprungen": "–", "fehler": "⚠" };

function renderSteps(box, steps) {
  box.hidden = !steps.length;
  box.replaceChildren(...steps.map((s) => el("div", { class: `step ${s.state.replace(" ", "-")}` },
    el("span", { class: "step-icon" }, STEP_ICONS[s.state] ?? ""),
    el("span", { class: "step-label" }, s.label),
    s.detail ? el("span", { class: "step-detail" }, s.detail) : null,
    s.state === "läuft" && s.progress != null
      ? el("div", { class: "bar step-bar" }, el("div", { style: `width:${s.progress}%` })) : null,
  )));
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
    if (!window.EventSource) return poll();
    const source = new EventSource(`/api/activities/${activity_id}/events`);
    source.onmessage = (event) => {
      const r = finish(JSON.parse(event.data));
      if (r.done) { source.close(); settle(r); }
    };
    source.onerror = () => { source.close(); poll(); };
  });
}

async function loadConfig() {
  const cfg = await api("/api/config");
  bitrate = cfg.bitrate;
  document.querySelector(`input[name=fmt][value=${cfg.audio_format}]`).checked = true;
  $("#dirs").textContent = `Musik: ${cfg.musik_dir} · Podcasts: ${cfg.podcast_dir} · ` +
    `${cfg.parallel_downloads} Downloads gleichzeitig`;
  $("#ffmpeg-warning").hidden = cfg.ffmpeg;
}

let bitrate = 320;

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
  $("#probe-error").hidden = true;
  $("#preview").hidden = true;
  showBusy($("#probe-busy"), "Die Schildkröte schaut sich das an …");
  try {
    const data = await runActivity("/api/probe", { url: $("#url").value, mode }, $("#probe-steps"));
    $("#probe-steps").hidden = true;
    preview = { title: data.title, mode, url: $("#url").value.trim(),
      items: data.items.map((i) => ({ ...i, selected: !i.already })) };
    $("#album").hidden = true;
    $("#album-hint").hidden = !data.album_video;
    renderPreview(data.is_playlist);
  } catch (err) {
    $("#probe-error").textContent = err.message;
    $("#probe-error").hidden = false;
  } finally {
    showBusy($("#probe-busy"), "");
    btn.disabled = false;
    btn.textContent = "Prüfen";
  }
});

function renderPreview(isPlaylist) {
  const cols = COLUMNS[preview.mode];
  $("#preview").hidden = false;
  $("#preview-title").textContent = isPlaylist ? preview.title : (preview.mode === "musik" ? "Titel" : "Video");
  $("#preview-count").textContent = `${preview.items.length} ${preview.items.length === 1 ? "Eintrag" : "Einträge"}`;

  const bulk = preview.mode === "musik" && preview.items.length > 1;
  $("#bulk").hidden = !bulk;
  if (bulk) {
    const first = preview.items[0];
    $("#bulk-album").value = first.album || "";
    $("#bulk-album-artist").value = first.album ? first.album_artist : "";
    $("#bulk-year").value = first.album ? first.year : "";
  }

  const allBox = el("input", { type: "checkbox", title: "Alle auswählen",
    checked: preview.items.every((i) => i.selected) });
  allBox.addEventListener("change", () => {
    preview.items.forEach((i) => (i.selected = allBox.checked));
    renderRows();
  });
  $("#preview-head").replaceChildren(
    el("th", {}, allBox), ...cols.map((c) => el("th", {}, c.label)), el("th", {}, "Original"));
  renderRows();
}

function renderRows() {
  const cols = COLUMNS[preview.mode];
  $("#preview-body").replaceChildren(...preview.items.map((item) => {
    const box = el("input", { type: "checkbox", checked: item.selected });
    box.addEventListener("change", () => (item.selected = box.checked));
    const cells = cols.map((c) => {
      const input = el("input", { type: c.type || "text", value: item[c.key] ?? "" });
      input.addEventListener("input", () => {
        item[c.key] = c.type === "number" ? (input.value ? Number(input.value) : null) : input.value;
      });
      return el("td", { class: c.cls || "" }, input);
    });
    const orig = el("td", { class: "orig" }, item.source_title,
      item.already ? el("div", {}, el("span", { class: "badge" }, "bereits geladen")) : null);
    return el("tr", { class: item.already ? "already" : "" }, el("td", {}, box), ...cells, orig);
  }));
}

const VA = "Various Artists";
const primaryArtist = (artist) => artist.split(/ feat\. |, /)[0];

let bulkArtistBeforeVa = "";
$("#bulk-va").addEventListener("change", () => {
  const field = $("#bulk-album-artist");
  if ($("#bulk-va").checked) {
    bulkArtistBeforeVa = field.value;
    field.value = VA;
    $("#bulk-same-artist").checked = false;
  } else {
    field.value = bulkArtistBeforeVa;
  }
  field.disabled = $("#bulk-va").checked;
  $("#bulk-same-artist").disabled = $("#bulk-va").checked;
});

$("#bulk-apply").addEventListener("click", () => {
  const album = $("#bulk-album").value.trim();
  const albumArtist = $("#bulk-album-artist").value.trim();
  const year = $("#bulk-year").value.trim();
  const sameArtist = $("#bulk-same-artist").checked && albumArtist;
  const total = preview.items.length;
  preview.items.forEach((item, index) => {
    if (sameArtist) item.artist = albumArtist;
    item.album = album;
    item.album_artist = album ? (albumArtist || item.album_artist) : primaryArtist(item.artist);
    item.track_no = album ? index + 1 : null;
    item.track_total = album ? total : null;
    if (year) item.year = year;
  });
  renderRows();
});

// ---------- Konflikt-Dialog: Überschreiben / Überspringen / Beide behalten ----------

const CONFLICT_CHOICES = [["keep_both", "Beide behalten (… (2))"], ["overwrite", "Überschreiben"], ["skip", "Überspringen"]];

function formatSize(bytes) {
  return bytes > 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;
}

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

$("#download-btn").addEventListener("click", async () => {
  const items = preview.items.filter((i) => i.selected).map(({ selected, already, ...rest }) => rest);
  if (!items.length) return;
  const btn = $("#download-btn");
  btn.disabled = true;
  try {
    const body = { title: preview.title || items[0].title, mode: preview.mode, audio_format: selectedFormat(), items };
    const decisions = await resolveConflicts(await api("/api/conflicts", body));
    if (decisions === null) return;
    items.forEach((i) => { if (decisions[i.id]) i.on_conflict = decisions[i.id]; });
    if (!items.some((i) => i.on_conflict !== "skip")) return;
    await api("/api/jobs", body);
    $("#preview").hidden = true;
    $("#url").value = "";
  } catch (err) {
    $("#probe-error").textContent = err.message;
    $("#probe-error").hidden = false;
  } finally {
    btn.disabled = false;
  }
});

function button(label, onClick, opts = {}) {
  const b = el("button", { type: "button", class: opts.cls || "secondary small-btn", title: opts.title || "" }, label);
  b.addEventListener("click", async () => {
    b.disabled = true;
    try { await onClick(); } catch (err) { alert(err.message); } finally { b.disabled = false; }
  });
  return b;
}

const openPath = (path) => api("/api/open", { path });
const copyText = (text) => navigator.clipboard.writeText(text);
const retry = (jobId, taskId = null) => api(`/api/jobs/${jobId}/retry`, { task_id: taskId });

function taskStatus(t) {
  if (t.status === "neuer Versuch") return `neuer Versuch in ${t.retry_in} s`;
  return t.status;
}

const cssName = (status) => status.replaceAll(" ", "-");

function progressBar(progress) {
  return el("div", { class: "bar" },
    el("div", { class: "fill", style: `width:${progress}%` }),
    el("div", { class: "runner", style: `left:${Math.min(97, Math.max(3, progress))}%` }));
}

function renderTask(job, t) {
  const actions = [];
  if (t.status === "fertig" && t.path) {
    actions.push(button("📂 Im Ordner öffnen", () => openPath(t.path), { title: "Im Explorer anzeigen" }));
    actions.push(button("Pfad kopieren", () => copyText(t.win_path)));
  }
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

function renderJobs(jobs) {
  $("#clear-jobs").hidden = !jobs.some((j) => j.done === j.total);
  if (!jobs.length) {
    $("#jobs").replaceChildren(el("div", { class: "empty" }, turtle("leer", { size: 72 }),
      el("span", {}, "Noch keine Downloads. Die Schildkröte wartet geduldig auf die erste URL.")));
    return;
  }
  $("#jobs").replaceChildren(...jobs.map((job) => {
    const head = [];
    if (job.folder) head.push(button("📂 Ordner öffnen", () => openPath(job.folder)));
    if (job.failed) head.push(button(`↻ ${job.failed} fehlgeschlagene wiederholen`, () => retry(job.id), { cls: "small-btn" }));
    const counter = `${job.done}/${job.total}` + (job.failed ? ` · ${job.failed} Fehler` : "") +
      (job.skipped ? ` · ${job.skipped} übersprungen` : "") + ` · ${(job.audio_format || "").toUpperCase()}`;
    return el("div", { class: "job" },
      el("h3", {}, el("span", {}, `${job.mode === "musik" ? "🎵" : "🎙️"} ${job.title}`),
        el("span", { class: "muted" }, counter)),
      head.length ? el("div", { class: "task-actions job-actions" }, ...head) : null,
      ...job.tasks.map((t) => renderTask(job, t)),
    );
  }));
}

/** Live-Updates der Job-Liste per Server-Sent Events; EventSource verbindet sich bei Abbruch selbst neu. */
function connectJobs() {
  if (!window.EventSource) {
    const poll = async () => { renderJobs(await api("/api/jobs").catch(() => [])); setTimeout(poll, 1000); };
    return poll();
  }
  const source = new EventSource("/api/jobs/events");
  source.onmessage = (event) => renderJobs(JSON.parse(event.data));
}

$("#clear-jobs").addEventListener("click", async () => {
  await api("/api/jobs", null, "DELETE");
});

// ---------- Album in einem Video ----------

let album = null; // { id, duration, peaks, tracks: [{start, artist, title}] }
const audio = $("#album-audio");
const wave = $("#wave");

function fmt(sec) {
  sec = Math.max(0, sec || 0);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const ss = s.toFixed(1).padStart(4, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

function parseTime(text) {
  const parts = text.trim().replace(",", ".").split(":").map(Number);
  if (!parts.length || parts.some(Number.isNaN)) return null;
  return parts.reduce((acc, v) => acc * 60 + v, 0);
}

function albumBusy(busy, text = "Die Schildkröte hört genau hin …") {
  document.querySelectorAll("#album button").forEach((b) => (b.disabled = busy));
  showBusy($("#album-busy"), busy ? text : "");
  if (busy) $("#album-error").hidden = true;
  else $("#album-steps").hidden = true;
}

function albumError(err) {
  $("#album-error").textContent = err.message;
  $("#album-error").hidden = false;
}

function sortTracks() {
  album.tracks.sort((a, b) => a.start - b.start);
}

function trackEnd(i) {
  return i + 1 < album.tracks.length ? album.tracks[i + 1].start : album.duration;
}

function setTracks(result, steps) {
  album.tracks = result.tracks.map((t) => ({ start: t.start, artist: t.artist, title: t.title }));
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
    album = { id: data.id, duration: data.duration, peaks: data.peaks, tracks: [], albumArtist: data.artist };
    showArtistCol = false;
    $("#album-va").checked = false;
    $("#album-artist").disabled = false;
    $("#album-name").value = data.album;
    $("#album-artist").value = data.artist;
    $("#album-year").value = data.year || "";
    $("#album-genre").value = "";
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

function renderHints(hints) {
  const box = $("#album-hints");
  box.hidden = !hints.length;
  box.replaceChildren("Weiterer Text im Bild (klicken = als Albuminterpret):",
    ...hints.map((h) => {
      const chip = el("button", { type: "button", class: "chip" }, h);
      chip.addEventListener("click", () => {
        if ($("#album-va").checked) return;
        $("#album-artist").value = h;
        setAlbumArtist(h);
      });
      return chip;
    }));
}

let showArtistCol = false;
let albumArtistBeforeVa = "";

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

$("#album-va").addEventListener("change", () => {
  const field = $("#album-artist");
  if ($("#album-va").checked) {
    albumArtistBeforeVa = field.value;
    field.value = VA;
    album.albumArtist = VA; // Interpreten der Titel bleiben einzeln erhalten
  } else {
    field.value = albumArtistBeforeVa;
    album.albumArtist = albumArtistBeforeVa;
  }
  field.disabled = $("#album-va").checked;
  $("#album-apply").disabled = $("#album-va").checked;
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
    const start = el("input", { value: fmt(t.start) });
    start.addEventListener("change", () => {
      const v = parseTime(start.value);
      if (v != null && v >= 0 && v < album.duration) t.start = v;
      renderAlbum();
    });
    const artist = el("input", { value: t.artist });
    artist.addEventListener("input", () => (t.artist = artist.value));
    const title = el("input", { value: t.title });
    title.addEventListener("input", () => (t.title = title.value));

    const play = el("button", { type: "button", class: "secondary", title: "Ab Start abspielen" }, "▶");
    play.addEventListener("click", () => { audio.currentTime = t.start; audio.play(); });
    const here = el("button", { type: "button", class: "secondary", title: "Start = aktuelle Abspielposition" }, "⇤ hier");
    here.addEventListener("click", () => { t.start = audio.currentTime; renderAlbum(); });
    const del = el("button", { type: "button", class: "secondary", title: "Grenze entfernen (mit vorherigem Titel zusammenfassen)" }, "✕");
    del.addEventListener("click", () => { album.tracks.splice(i, 1); renderAlbum(); });

    return el("tr", { class: i === playing ? "playing" : "" },
      el("td", { class: "dur" }, String(i + 1)),
      el("td", { class: "time" }, start),
      el("td", { class: "dur" }, fmt(trackEnd(i) - t.start).replace(/\.\d$/, "")),
      el("td", {}, artist), el("td", {}, title),
      el("td", { class: "actions" }, play, here, del));
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
  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue("--frame").trim();
  const muted = css.getPropertyValue("--muted").trim();
  const text = css.getPropertyValue("--text").trim();

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
    album.tracks.forEach((t) => delete t.on_conflict);
    const body = {
      album: $("#album-name").value, album_artist: $("#album-artist").value,
      year: $("#album-year").value, genre: $("#album-genre").value,
      audio_format: selectedFormat(), tracks: album.tracks,
    };
    const decisions = await resolveConflicts(await api(`/api/album/${album.id}/conflicts`, body));
    if (decisions === null) return;
    // Titel-IDs vergibt der Server in Start-Reihenfolge: <video-id>-01, -02 …
    album.tracks.forEach((t, i) => {
      const choice = decisions[`${album.id}-${String(i + 1).padStart(2, "0")}`];
      if (choice) t.on_conflict = choice;
    });
    if (!album.tracks.some((t) => t.on_conflict !== "skip")) return;
    await api(`/api/album/${album.id}/jobs`, body);
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
