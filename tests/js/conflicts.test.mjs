import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { submitWithConflicts } from "../../ytdl/static/js/conflicts.js";

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

/** Fake-Server: /conflicts liefert `found`, /jobs merkt sich den Body. */
function server(found) {
  const posted = [];
  globalThis.fetch = async (path, init) => {
    const body = JSON.parse(init.body);
    if (path.endsWith("/conflicts")) return { ok: true, status: 200, json: async () => found };
    posted.push({ path, body });
    return { ok: true, status: 200, json: async () => ({ id: "job" }) };
  };
  return posted;
}

const body = { mode: "musik", items: [{ id: "a" }, { id: "b" }] };

test("without conflicts the job is created right away", async () => {
  const posted = server([]);
  const dialog = () => assert.fail("kein Dialog ohne Konflikte");
  assert.equal(await submitWithConflicts("/api/conflicts", "/api/jobs", body, 2, async (c) => (c.length ? dialog() : {})), true);
  assert.deepEqual(posted, [{ path: "/api/jobs", body: { ...body, decisions: {} } }]);
});

test("decisions are sent by id", async () => {
  const posted = server([{ id: "b" }]);
  assert.equal(await submitWithConflicts("/c/conflicts", "/c/jobs", body, 2, async () => ({ b: "overwrite" })), true);
  assert.deepEqual(posted[0].body.decisions, { b: "overwrite" });
});

test("cancel and all-skipped create no job", async () => {
  let posted = server([{ id: "a" }]);
  assert.equal(await submitWithConflicts("/c/conflicts", "/c/jobs", body, 2, async () => null), false);
  posted = server([{ id: "a" }, { id: "b" }]);
  assert.equal(await submitWithConflicts("/c/conflicts", "/c/jobs", body, 2, async () => ({ a: "skip", b: "skip" })), false);
  assert.deepEqual(posted, []);
  posted = server([{ id: "a" }]);
  assert.equal(await submitWithConflicts("/c/conflicts", "/c/jobs", body, 2, async () => ({ a: "skip" })), true);
  assert.equal(posted.length, 1); // b wird trotzdem geladen
});
