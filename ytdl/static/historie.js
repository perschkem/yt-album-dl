import { api } from "./js/api.js";
import { $, button, el, emptyState } from "./js/dom.js";
import { cssName, formatSize, formatTime, plural } from "./js/format.js";
import { has, t } from "./js/i18n.js";

const PAGE = 20; // Downloads pro Seite
let offset = 0;

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

function videoLink(entry) {
  if (!entry.url) return null;
  const url = entry.start ? `${entry.url}${entry.url.includes("?") ? "&" : "?"}t=${Math.floor(entry.start)}` : entry.url;
  return el("a", { href: url, target: "_blank", rel: "noopener" }, entry.start ? `Video ab ${formatTime(entry.start)} öffnen` : "Video öffnen");
}

/** Übersetzter Code – ältere Einträge enthalten noch den deutschen Klartext, der dann so erscheint. */
const label = (section, value) => (has(`${section}.${value}`) ? t(`${section}.${value}`) : value);

function tagRows(e) {
  const tags = e.tags || {};
  const rows = Object.entries(TAG_LABELS).filter(([k]) => tags[k] != null && tags[k] !== "")
    .map(([k, name]) => el("tr", {}, el("th", {}, name), el("td", {}, String(tags[k]))));
  rows.push(el("tr", {}, el("th", {}, "Cover"), el("td", {}, t(`cover.${e.cover}`) + (e.cover_url ? ` (${e.cover_url})` : ""))));
  rows.push(el("tr", {}, el("th", {}, "Format"), el("td", {}, `${(e.format || "").toUpperCase()}${e.bitrate ? ` · ${e.bitrate} kbit/s` : ""}`)));
  if (e.start != null) rows.push(el("tr", {}, el("th", {}, "Ausschnitt"), el("td", {}, `${formatTime(e.start)} – ${formatTime(e.end)}`)));
  if (e.boundary_source) rows.push(el("tr", {}, el("th", {}, "Grenzen aus"), el("td", {}, label("source", e.boundary_source))));
  if (e.source_title) rows.push(el("tr", {}, el("th", {}, "Originaltitel"), el("td", {}, e.source_title)));
  rows.push(el("tr", {}, el("th", {}, "Versuche"), el("td", {}, String(e.attempts || 1))));
  if (e.with_cookies) rows.push(el("tr", {}, el("th", {}, "Anmeldung"),
    el("td", {}, "mit YouTube-Anmeldung (Cookies) – YouTube hatte eine Bot-Prüfung verlangt")));
  return rows;
}

/** Ein Titel innerhalb eines Downloads – aufklappbar für Tags und Details. */
function renderTitle(e) {
  const tags = e.tags || {};
  const label = [tags.artist, tags.title].filter(Boolean).join(" - ") || e.source_title || e.url;
  const status = cssName(e.result);
  const link = videoLink(e);
  return el("details", { class: `hist-title ${status}` },
    el("summary", {},
      el("span", { class: "hist-nr muted small" }, tags.track_no ? String(tags.track_no).padStart(2, "0") : ""),
      el("span", { class: "hist-label" }, label),
      el("span", { class: `status ${status}` }, t(`status.${e.result}`))),
    e.path ? el("div", { class: "path" }, [e.win_path || e.path, formatSize(e.size)].filter(Boolean).join(" · ")) : null,
    e.path && !e.exists ? el("div", { class: "err" }, "Die Datei existiert nicht mehr an diesem Ort.") : null,
    e.error ? el("div", { class: "err" }, e.error) : null,
    el("table", { class: "hist-tags" }, el("tbody", {}, ...tagRows(e))),
    link ? el("div", { class: "task-actions" }, link) : null,
  );
}

/** Ein Download (Job) wie in der Download-Liste: Kopf mit Zähler und „Ordner öffnen“, Titel zum Ausklappen. */
function renderGroup(g) {
  const when = new Date(g.ts * 1000).toLocaleString("de-DE");
  const parts = [`${g.count} Titel`];
  for (const [result, n] of Object.entries(g.counts)) parts.push(`${n} ${t(`status.${result}`)}`);
  if (g.format) parts.push(g.format.toUpperCase());
  const failed = g.counts.failed || 0;

  const head = el("summary", { class: "hist-group-head" },
    el("span", { class: "hist-group-title" }, `${g.mode === "musik" ? "🎵" : "🎙️"} ${g.title || "Download"}`),
    el("span", { class: "muted small" }, `${when} · ${parts.join(" · ")}`));
  const actions = [];
  if (g.folder) actions.push(button("📂 Ordner öffnen", () => api("/api/open", { path: g.folder }), { cls: "small-btn" }));
  return el("details", { class: `job hist-group${failed ? " has-errors" : ""}` },
    head,
    actions.length ? el("div", { class: "task-actions job-actions" }, ...actions) : null,
    el("div", { class: "hist-titles" }, ...g.entries.map(renderTitle)),
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
    list.replaceChildren(emptyState(filters().toString() ? "Keine Einträge für diese Filter." : "Noch keine Einträge."));
  }
  list.append(...data.groups.map(renderGroup));
  offset += data.groups.length;
  $("#hist-count").textContent = `${plural(data.total, "Download", "Downloads")} · ${data.entries_total} Titel`;
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
