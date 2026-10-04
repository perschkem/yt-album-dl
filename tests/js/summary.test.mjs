import assert from "node:assert/strict";
import { test } from "node:test";

import { jobCounter, summarize, taskStatus } from "../../ytdl/static/js/summary.js";
import { useLanguage } from "./locale.mjs";

const task = (status, progress = 0, extra = {}) => ({ status, progress, ...extra });
const job = (title, tasks) => ({ title, tasks });

test("taskStatus shows countdowns", () => {
  assert.equal(taskStatus(task("retrying", 0, { retry_in: 8 })), "neuer Versuch in 8 s");
  assert.equal(taskStatus(task("paused", 0, { retry_in: 61 })), "pausiert · noch 2 min");
  assert.equal(taskStatus(task("downloading")), "lädt");
  useLanguage("en");
  assert.equal(taskStatus(task("retrying", 0, { retry_in: 8 })), "retrying in 8 s");
  useLanguage("de");
});

test("empty list has no summary", () => {
  assert.equal(summarize([]), null);
});

test("running counts only active downloads", () => {
  const jobs = [
    job("Neu", [task("done", 100), task("downloading", 50), task("failed")]),
    job("Alt", [task("done", 100), task("done", 100)]), // abgeschlossen → zählt nicht mit
  ];
  const s = summarize(jobs);
  assert.equal(s.state, "running");
  assert.equal(s.text, "Neu: 2 von 3 fertig · 1 läuft · 1 Fehler");
  assert.equal(s.progress, 250 / 3);
});

test("several active downloads have no title prefix", () => {
  const s = summarize([job("A", [task("downloading")]), job("B", [task("waiting"), task("waiting")])]);
  assert.equal(s.text, "0 von 3 fertig · 3 laufen");
});

test("finished: newest download decides", () => {
  assert.deepEqual(summarize([job("A", [task("done", 100), task("skipped")]), job("B", [task("failed")])]),
    { state: "done", icon: "✓", text: "Alle Downloads fertig · 1 übersprungen" });
  assert.equal(summarize([job("B", [task("failed")])]).state, "failed");
});

test("bot check pause wins", () => {
  const s = summarize([job("A", [task("paused", 0, { retry_in: 600 }), task("paused", 0, { retry_in: 300 }),
    task("done", 100)])]);
  assert.equal(s.state, "paused");
  assert.match(s.text, /pausieren noch ca\. 10 min \(1 von 3 fertig\)/);
});

test("jobCounter", () => {
  assert.equal(jobCounter({ done: 3, total: 5, failed: 1, skipped: 0, audio_format: "mp3" }), "3/5 · 1 Fehler · MP3");
  assert.equal(jobCounter({ done: 1, total: 1, failed: 0, skipped: 1, audio_format: "" }), "1/1 · 1 übersprungen");
});
