// Download-Liste: Live-Updates, Zusammenfassung, Ein-/Ausklappen, Hinweis zur YouTube-Anmeldung.

import { api, subscribe } from "./api.js";
import { $, button, el, emptyState } from "./dom.js";
import { avgProgress, cssName } from "./format.js";
import { locale, t } from "./i18n.js";
import { progressBar } from "./progress.js";
import { openSettings } from "./settings.js";
import { jobCounter, summarize, taskStatus } from "./summary.js";

const openPath = (path) => api("/api/open", { path });
const retry = (jobId, taskId = null) => api(`/api/jobs/${jobId}/retry`, { task_id: taskId });

function renderTask(job, task) {
  const actions = [];
  if (task.status === "failed") actions.push(button(t("jobs.retry_one"), () => retry(job.id, task.id), { cls: "small-btn" }));
  return el("div", { class: `task ${cssName(task.status)}` },
    el("div", { class: "task-head" }, el("span", {}, task.label),
      el("span", { class: `status ${cssName(task.status)}` }, taskStatus(task))),
    progressBar(task.progress),
    task.detail ? el("div", { class: "detail" }, task.detail) : null,
    task.win_path ? el("div", { class: "path" }, task.win_path) : null,
    task.error ? el("div", { class: "err" }, task.error) : null,
    actions.length ? el("div", { class: "task-actions" }, ...actions) : null,
  );
}


function renderSummary(jobs) {
  const box = $("#jobs-summary");
  const summary = summarize(jobs);
  box.hidden = !summary;
  if (!summary) return;
  box.className = `jobs-summary ${summary.state}`;
  box.replaceChildren(el("span", { class: "summary-icon" }, summary.icon), el("span", {}, summary.text));
  if (summary.state === "paused") {
    // Nach dem Hinterlegen von Cookies sofort weitermachen
    box.append(button(t("jobs.resume"), () => api("/api/jobs/resume", {}), { cls: "small-btn" }),
      el("button", { type: "button", class: "small-btn", onclick: openSettings }, t("auth.setup")));
  } else if (summary.state === "running") {
    box.append(progressBar(summary.progress));
  }
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
  $("#toggle-jobs").textContent = jobs.length && jobs.every((j) => collapsedJobs.has(j.id)) ? t("jobs.expand_all") : t("jobs.collapse_all");
  if (!jobs.length) {
    $("#jobs").replaceChildren(emptyState(t("jobs.empty")));
    return;
  }
  $("#jobs").replaceChildren(...jobs.map((job) => {
    const head = [];
    // „Ordner öffnen“ nur einmal pro Job; bei einem einzelnen Titel wird die Datei im Explorer markiert
    const finished = job.tasks.filter((task) => task.path);
    if (job.folder) {
      const target = finished.length === 1 ? finished[0].path : job.folder;
      head.push(button(t("jobs.open_folder"), () => openPath(target), { title: t("jobs.open_folder_hint") }));
    }
    if (job.failed) head.push(button(t("jobs.retry_failed", { count: job.failed }), () => retry(job.id), { cls: "small-btn" }));
    const collapsed = collapsedJobs.has(job.id);
    const title = el("h3", { title: t(collapsed ? "jobs.expand" : "jobs.collapse") },
      el("span", { class: "job-title" }, `${job.mode === "musik" ? "🎵" : "🎙️"} ${job.title}`),
      el("span", { class: "muted" }, jobCounter(job)));
    title.addEventListener("click", () => toggleJob(job.id));
    const running = job.done < job.total;
    const card = el("div", { class: `job${collapsed ? " collapsed" : ""}` }, title);
    if (collapsed) {
      // eingeklappt: nur Kopf, bei laufendem Download mit Gesamtbalken
      if (running) card.append(Object.assign(progressBar(avgProgress(job.tasks)), { className: "bar job-bar" }));
      return card;
    }
    if (head.length) card.append(el("div", { class: "task-actions job-actions" }, ...head));
    card.append(...job.tasks.map((task) => renderTask(job, task)));
    return card;
  }));
}

const clockTime = (ts) => new Date(ts * 1000).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });

/** Hinweis oben, wenn YouTube eine Bot-Prüfung verlangt hat – damit man merkt, dass gerade mit
 *  Anmeldung geladen wird bzw. warum Downloads pausieren. */
function renderAuthNotice(auth) {
  const box = $("#auth-notice");
  const show = auth && (auth.cookies_active || auth.recent_bot_check);
  box.hidden = !show;
  if (!show) return;
  const when = auth.last_bot_check ? t("auth.when", { time: clockTime(auth.last_bot_check) }) : "";
  const key = auth.cookies_active ? "auth.active" : auth.cookies_configured ? "auth.failed_with_cookies" : "auth.no_cookies";
  $("#auth-notice-text").textContent = t(key, { when, until: auth.cookies_until ? clockTime(auth.cookies_until) : "" });
  $("#auth-notice-open").hidden = auth.cookies_active;
}

$("#auth-notice-open").addEventListener("click", openSettings);

/** Live-Updates der Job-Liste (und des Anmeldestatus) per Server-Sent Events; EventSource verbindet sich
 *  bei Abbruch selbst neu. */
export function connectJobs() {
  subscribe("/api/jobs/events", (data) => {
    renderJobs(data.jobs);
    renderAuthNotice(data.auth);
  });
}

$("#clear-jobs").addEventListener("click", async () => {
  await api("/api/jobs", null, "DELETE");
});
