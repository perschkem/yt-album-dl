const $ = (sel) => document.querySelector(sel);
const PAGE = 50;
let offset = 0;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k in node) node[k] = v;
    else node.setAttribute(k, v);
  }
  node.append(...children.filter((c) => c != null && c !== ""));
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

function filters() {
  const params = new URLSearchParams();
  for (const [key, id] of [["q", "#hist-q"], ["mode", "#hist-mode"], ["result", "#hist-result"], ["days", "#hist-days"]]) {
    const value = $(id).value.trim();
    if (value) params.set(key, value);
  }
  return params;
}

const TAG_LABELS = { artist: "Interpret", title: "Titel", album: "Album", album_artist: "Albuminterpret",
  track_no: "Tracknummer", track_total: "Titel gesamt", year: "Jahr", date: "Datum", genre: "Genre" };

function clock(sec) {
  const s = Math.round(sec || 0);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return (h ? `${h}:${String(m).padStart(2, "0")}` : `${m}`) + `:${String(r).padStart(2, "0")}`;
}

function sizeText(bytes) {
  return bytes ? `${(bytes / 1_048_576).toFixed(1)} MB` : "";
}

function videoLink(entry) {
  if (!entry.url) return null;
  const url = entry.start ? `${entry.url}${entry.url.includes("?") ? "&" : "?"}t=${Math.floor(entry.start)}` : entry.url;
  return el("a", { href: url, target: "_blank", rel: "noopener" }, entry.start ? `Video ab ${clock(entry.start)} öffnen` : "Video öffnen");
}

function renderEntry(e) {
  const t = e.tags || {};
  const label = [t.artist, t.title].filter(Boolean).join(" - ") || e.source_title || e.url;
  const when = new Date(e.ts * 1000).toLocaleString("de-DE");
  const status = e.result.replace(" ", "-");

  const rows = Object.entries(TAG_LABELS).filter(([k]) => t[k] != null && t[k] !== "")
    .map(([k, name]) => el("tr", {}, el("th", {}, name), el("td", {}, String(t[k]))));
  rows.push(el("tr", {}, el("th", {}, "Cover"), el("td", {}, e.cover + (e.cover_url ? ` (${e.cover_url})` : ""))));
  rows.push(el("tr", {}, el("th", {}, "Format"), el("td", {}, `${(e.format || "").toUpperCase()}${e.bitrate ? ` · ${e.bitrate} kbit/s` : ""}`)));
  if (e.start != null) rows.push(el("tr", {}, el("th", {}, "Ausschnitt"), el("td", {}, `${clock(e.start)} – ${clock(e.end)}`)));
  if (e.boundary_source) rows.push(el("tr", {}, el("th", {}, "Grenzen aus"), el("td", {}, e.boundary_source)));
  if (e.source_title) rows.push(el("tr", {}, el("th", {}, "Originaltitel"), el("td", {}, e.source_title)));
  rows.push(el("tr", {}, el("th", {}, "Versuche"), el("td", {}, String(e.attempts || 1))));

  const actions = [];
  if (e.path && e.exists) {
    const open = el("button", { type: "button", class: "small-btn" }, "📂 Im Ordner öffnen");
    open.addEventListener("click", () => api("/api/open", { path: e.path }).catch((err) => alert(err.message)));
    actions.push(open);
  }
  const link = videoLink(e);
  if (link) actions.push(link);

  return el("details", { class: `job hist ${status}` },
    el("summary", {},
      el("span", { class: "hist-when muted small" }, when),
      el("span", { class: `status ${status}` }, e.result),
      el("span", { class: "hist-label" }, `${e.mode === "musik" ? "🎵" : "🎙️"} ${label}`),
      el("span", { class: "hist-album muted small" }, t.album || "")),
    e.path ? el("div", { class: "path" }, `${e.win_path || e.path}${sizeText(e.size) ? ` · ${sizeText(e.size)}` : ""}`) : null,
    e.path && !e.exists ? el("div", { class: "err" }, "Die Datei existiert nicht mehr an diesem Ort.") : null,
    e.error ? el("div", { class: "err" }, e.error) : null,
    el("table", { class: "hist-tags" }, el("tbody", {}, ...rows)),
    actions.length ? el("div", { class: "task-actions" }, ...actions) : null,
  );
}

async function load(reset = true) {
  if (reset) offset = 0;
  const params = filters();
  params.set("limit", PAGE);
  params.set("offset", offset);
  const data = await api(`/api/history?${params}`);
  const list = $("#hist-list");
  if (reset) list.replaceChildren();
  if (!data.total) {
    list.replaceChildren(el("div", { class: "empty" }, el("img", { src: "img/turtles/platzhalter.svg", alt: "", width: 72, height: 40, class: "turtle" }),
      el("span", {}, filters().toString() ? "Keine Einträge für diese Filter." : "Noch keine Einträge.")));
  }
  list.append(...data.entries.map(renderEntry));
  offset += data.entries.length;
  $("#hist-count").textContent = `${data.total} ${data.total === 1 ? "Eintrag" : "Einträge"}`;
  $("#hist-more").hidden = offset >= data.total;
  $("#hist-csv").href = `/api/history.csv?${filters()}`;
}

let timer = null;
$("#hist-q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => load(), 250); });
for (const id of ["#hist-mode", "#hist-result", "#hist-days"]) $(id).addEventListener("change", () => load());
$("#hist-filter").addEventListener("submit", (event) => { event.preventDefault(); load(); });
$("#hist-more").addEventListener("click", () => load(false));
$("#hist-clear").addEventListener("click", async () => {
  if (!confirm("Die komplette Historie löschen? Die heruntergeladenen Dateien bleiben erhalten.")) return;
  await api("/api/history", null, "DELETE");
  load();
});

load();
