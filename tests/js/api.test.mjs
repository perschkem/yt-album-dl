import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import { api } from "../../ytdl/static/js/api.js";

const realFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = realFetch; });

function respond(status, body) {
  const calls = [];
  globalThis.fetch = async (path, init) => {
    calls.push({ path, init });
    return { ok: status < 400, status, json: async () => (body === undefined ? Promise.reject(new Error("kein JSON")) : body) };
  };
  return calls;
}

test("GET without body, POST with JSON body, other methods", async () => {
  let calls = respond(200, { ok: 1 });
  assert.deepEqual(await api("/api/config"), { ok: 1 });
  assert.equal(calls[0].init, undefined);

  calls = respond(200, {});
  await api("/api/jobs", { a: 1 });
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.body, '{"a":1}');

  calls = respond(200, {});
  await api("/api/jobs", null, "DELETE");
  assert.equal(calls[0].init.method, "DELETE");
  assert.equal(calls[0].init.body, undefined);
});

test("error with text detail", async () => {
  respond(400, { detail: "Keine Titel ausgewählt" });
  await assert.rejects(api("/api/jobs", {}), { message: "Keine Titel ausgewählt" });
});

test("error with field messages and missing folder", async () => {
  respond(400, { detail: { message: "Einstellungen nicht gespeichert", fields: { bitrate: "Erlaubt: …" } } });
  await assert.rejects(api("/api/settings", {}, "PUT"), (err) => {
    assert.equal(err.message, "Einstellungen nicht gespeichert");
    assert.deepEqual(err.fields, { bitrate: "Erlaubt: …" });
    return true;
  });
  respond(400, { detail: "Kein Ordner für Musik eingestellt", missing_folder: true });
  await assert.rejects(api("/api/jobs", {}), (err) => err.missingFolder === true);
});

test("validation list and non-JSON errors fall back to the status", async () => {
  respond(422, { detail: [{ loc: ["body", "url"], msg: "Field required" }] });
  await assert.rejects(api("/api/probe", {}), (err) => err.message === "Fehler 422" && !Object.keys(err.fields).length);
  respond(500, undefined);
  await assert.rejects(api("/api/jobs"), { message: "Fehler 500" });
});
