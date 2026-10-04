import { api } from "./js/api.js";
import { $, button, el, emptyState } from "./js/dom.js";
import { cssName, formatSize, formatTime } from "./js/format.js";
import { has, locale, t } from "./js/i18n.js";

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

// Tag → Schlüssel der Beschriftung
const TAG_LABELS = { artist: "tags.artist", title: "tags.title", album: "tags.album", album_artist: "tags.album_artist",
  track_no: "hist.track_number", track_total: "tags.track_total", year: "tags.year", date: "tags.date", genre: "tags.genre" };

function videoLink(entry) {
  if (!entry.url) return null;
  const url = entry.start ? `${entry.url}${entry.url.includes("?") ? "&" : "?"}t=${Math.floor(entry.start)}` : entry.url;
  return el("a", { href: url, target: "_blank", rel: "noopener" }, entry.start ? t("hist.video_from", { time: formatTime(entry.start) }) : t("hist.video"));
}

/** Übersetzter Code – ältere Einträge enthalten noch den deutschen Klartext, der dann so erscheint. */
const codeLabel = (section, value) => (has(`${section}.${value}`) ? t(`${section}.${value}`) : value);
const row = (key, value) => el("tr", {}, el("th", {}, t(key)), el("td", {}, value));

function tagRows(e) {
  const tags = e.tags || {};
  const rows = Object.entries(TAG_LABELS).filter(([k]) => tags[k] != null && tags[k] !== "")
    .map(([k, key]) => row(key, String(tags[k])));
  rows.push(row("hist.cover", codeLabel("cover", e.cover) + (e.cover_url ? ` (${e.cover_url})` : "")));
  rows.push(row("hist.format", `${(e.format || "").toUpperCase()}${e.bitrate ? ` · ${e.bitrate} kbit/s` : ""}`));
  if (e.start != null) rows.push(row("hist.excerpt", `${formatTime(e.start)} – ${formatTime(e.end)}`));
  if (e.boundary_source) rows.push(row("hist.boundaries_from", codeLabel("source", e.boundary_source)));
  if (e.source_title) rows.push(row("hist.source_title", e.source_title));
  rows.push(row("hist.attempts", String(e.attempts || 1)));
  if (e.with_cookies) rows.push(row("hist.sign_in", t("hist.with_cookies")));
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
    e.path && !e.exists ? el("div", { class: "err" }, t("hist.file_missing")) : null,
    e.error ? el("div", { class: "err" }, e.error) : null,
    el("table", { class: "hist-tags" }, el("tbody", {}, ...tagRows(e))),
    link ? el("div", { class: "task-actions" }, link) : null,
  );
}

/** Ein Download (Job) wie in der Download-Liste: Kopf mit Zähler und „Ordner öffnen“, Titel zum Ausklappen. */
function renderGroup(g) {
  const when = new Date(g.ts * 1000).toLocaleString(locale());
  const parts = [t("hist.titles", { count: g.count })];
  for (const [result, n] of Object.entries(g.counts)) parts.push(`${n} ${t(`status.${result}`)}`);
  if (g.format) parts.push(g.format.toUpperCase());
  const failed = g.counts.failed || 0;

  const head = el("summary", { class: "hist-group-head" },
    el("span", { class: "hist-group-title" }, `${g.mode === "musik" ? "🎵" : "🎙️"} ${g.title || t("hist.untitled")}`),
    el("span", { class: "muted small" }, `${when} · ${parts.join(" · ")}`));
  const actions = [];
  if (g.folder) actions.push(button(t("jobs.open_folder"), () => api("/api/open", { path: g.folder }), { cls: "small-btn" }));
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
    list.replaceChildren(emptyState(t(filters().toString() ? "hist.empty_filtered" : "hist.empty")));
  }
  list.append(...data.groups.map(renderGroup));
  offset += data.groups.length;
  $("#hist-count").textContent = `${t("hist.downloads", { count: data.total })} · ${t("hist.titles", { count: data.entries_total })}`;
  $("#hist-more").hidden = offset >= data.total;
  $("#hist-csv").href = `/api/history.csv?${filters()}`;
}

let timer = null;
$("#hist-q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => load(), 250); });
for (const id of ["#hist-mode", "#hist-result", "#hist-days"]) $(id).addEventListener("change", () => load());
$("#hist-filter").addEventListener("submit", (event) => { event.preventDefault(); load(); });
$("#hist-more").addEventListener("click", () => load(false));
$("#hist-clear").addEventListener("click", async () => {
  if (!confirm(t("hist.clear_confirm"))) return;
  await api("/api/history", null, "DELETE");
  load();
});

load();
