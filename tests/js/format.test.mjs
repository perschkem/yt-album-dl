import assert from "node:assert/strict";
import { test } from "node:test";

import {
  avgProgress, countDone, countStatus, cssName, formatSize, formatTime, isChanged, parseTime, primaryArtist,
  sameValue, snapshot,
} from "../../ytdl/static/js/format.js";

test("formatTime", () => {
  assert.equal(formatTime(0), "0:00");
  assert.equal(formatTime(65.4), "1:05");
  assert.equal(formatTime(3725), "1:02:05");
  assert.equal(formatTime(-3), "0:00");
  assert.equal(formatTime(undefined), "0:00");
  assert.equal(formatTime(65.44, { tenths: true }), "1:05.4");
  assert.equal(formatTime(3601.5, { tenths: true }), "1:00:01.5");
  assert.equal(formatTime(5, { tenths: true }), "0:05.0");
});

test("parseTime", () => {
  assert.equal(parseTime("4:12"), 252);
  assert.equal(parseTime("1:02:03.5"), 3723.5);
  assert.equal(parseTime(" 75 "), 75);
  assert.equal(parseTime("1:05,5"), 65.5);
  assert.equal(parseTime(""), null);
  assert.equal(parseTime("1:xx"), null);
  assert.equal(parseTime(formatTime(3723.5, { tenths: true })), 3723.5);
});

test("formatSize", () => {
  assert.equal(formatSize(0), "");
  assert.equal(formatSize(null), "");
  assert.equal(formatSize(100), "1 KB");
  assert.equal(formatSize(512 * 1024), "512 KB");
  assert.equal(formatSize(5 * 1_048_576), "5.0 MB");
});

test("cssName", () => {
  assert.equal(cssName("a b c"), "a-b-c");
  assert.equal(cssName("waiting_for_convert"), "waiting_for_convert");
});

test("task counts and average progress", () => {
  const tasks = [
    { status: "done", progress: 100 }, { status: "failed", progress: 10 },
    { status: "skipped", progress: 0 }, { status: "downloading", progress: 50 },
  ];
  assert.equal(countDone(tasks), 3);
  assert.equal(countStatus(tasks, "failed"), 1);
  assert.equal(avgProgress(tasks), 87.5); // Fehler/übersprungen zählen als 100 %
  assert.equal(avgProgress([]), 0);
});

test("change tracking", () => {
  const keys = ["title", "track_no"];
  const orig = snapshot({ title: "A", track_no: 3, other: 1 }, keys);
  assert.deepEqual(orig, { title: "A", track_no: 3 });
  assert.equal(isChanged({ title: "A", track_no: "3" }, orig, keys), false); // Eingabefeld liefert Text
  assert.equal(isChanged({ title: "B", track_no: 3 }, orig, keys), true);
  assert.equal(isChanged({ title: "B" }, undefined, keys), false); // von Hand hinzugefügt
  assert.ok(sameValue(null, ""));
  assert.ok(!sameValue(0, ""));
});

test("primaryArtist", () => {
  assert.equal(primaryArtist("A feat. B"), "A");
  assert.equal(primaryArtist("A, B"), "A");
  assert.equal(primaryArtist("AC/DC"), "AC/DC");
});

test("numberSelected", async () => {
  const { numberSelected } = await import("../../ytdl/static/js/format.js");
  const items = [{ selected: true }, { selected: false, track_no: 9 }, { selected: true }];
  numberSelected(items);
  assert.deepEqual(items.map((i) => [i.track_no, i.track_total]), [[1, 2], [null, null], [2, 2]]);
});
