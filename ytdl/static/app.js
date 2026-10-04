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
let polling = null;

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

async function api(path, body) {
  const res = await fetch(path, body ? {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  } : undefined);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Fehler ${res.status}`);
  return data;
}

async function loadConfig() {
  const cfg = await api("/api/config");
  $("#dirs").textContent = `Musik: ${cfg.musik_dir} · Podcasts: ${cfg.podcast_dir} · MP3 ${cfg.bitrate} kbit/s`;
  $("#ffmpeg-warning").hidden = cfg.ffmpeg;
}

function selectedMode() {
  return document.querySelector("input[name=mode]:checked").value;
}

$("#probe-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const btn = $("#probe-btn");
  const mode = selectedMode();
  btn.disabled = true;
  btn.textContent = "Lade Infos …";
  $("#probe-error").hidden = true;
  try {
    const data = await api("/api/probe", { url: $("#url").value, mode });
    preview = { title: data.title, mode, items: data.items.map((i) => ({ ...i, selected: !i.already })) };
    renderPreview(data.is_playlist);
  } catch (err) {
    $("#probe-error").textContent = err.message;
    $("#probe-error").hidden = false;
  } finally {
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

$("#bulk-apply").addEventListener("click", () => {
  const album = $("#bulk-album").value.trim();
  const albumArtist = $("#bulk-album-artist").value.trim();
  const year = $("#bulk-year").value.trim();
  const total = preview.items.length;
  preview.items.forEach((item, index) => {
    item.album = album;
    item.album_artist = album ? (albumArtist || item.album_artist) : item.artist.split(/ feat\. |, /)[0];
    item.track_no = album ? index + 1 : null;
    item.track_total = album ? total : null;
    if (year) item.year = year;
  });
  renderRows();
});

$("#download-btn").addEventListener("click", async () => {
  const items = preview.items.filter((i) => i.selected).map(({ selected, already, ...rest }) => rest);
  if (!items.length) return;
  const btn = $("#download-btn");
  btn.disabled = true;
  try {
    await api("/api/jobs", { title: preview.title || items[0].title, mode: preview.mode, items });
    $("#preview").hidden = true;
    $("#url").value = "";
    startPolling();
  } catch (err) {
    $("#probe-error").textContent = err.message;
    $("#probe-error").hidden = false;
  } finally {
    btn.disabled = false;
  }
});

function renderJobs(jobs) {
  if (!jobs.length) return;
  $("#jobs").replaceChildren(...jobs.map((job) => el("div", { class: "job" },
    el("h3", {}, el("span", {}, `${job.mode === "musik" ? "🎵" : "🎙️"} ${job.title}`),
      el("span", { class: "muted" }, `${job.done}/${job.total}`)),
    ...job.tasks.map((t) => el("div", { class: `task ${t.status}` },
      el("div", { class: "task-head" }, el("span", {}, t.label), el("span", { class: `status ${t.status}` }, t.status)),
      el("div", { class: "bar" }, el("div", { style: `width:${t.progress}%` })),
      t.path ? el("div", { class: "path" }, t.path) : null,
      t.error ? el("div", { class: "err" }, t.error) : null,
    )),
  )));
}

async function refreshJobs() {
  const jobs = await api("/api/jobs");
  renderJobs(jobs);
  const active = jobs.some((j) => j.done < j.total);
  if (!active && polling) {
    clearInterval(polling);
    polling = null;
  }
}

function startPolling() {
  if (!polling) polling = setInterval(refreshJobs, 1000);
  refreshJobs();
}

loadConfig();
startPolling();
