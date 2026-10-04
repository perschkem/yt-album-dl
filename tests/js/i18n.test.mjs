import assert from "node:assert/strict";
import { test } from "node:test";

import { language, setMessages, t } from "../../ytdl/static/js/i18n.js";

test("placeholders, plurals and unknown keys", () => {
  setMessages("de", { hello: "Hallo {name}", items: { one: "{count} Titel", other: "{count} Titel gesamt" } });
  assert.equal(language(), "de");
  assert.equal(t("hello", { name: "Welt" }), "Hallo Welt");
  assert.equal(t("hello"), "Hallo {name}"); // fehlender Parameter bleibt sichtbar
  assert.equal(t("items", { count: 1 }), "1 Titel");
  assert.equal(t("items", { count: 3 }), "3 Titel gesamt");
  assert.equal(t("gibt.es.nicht"), "gibt.es.nicht");
});

test("english plural rules", () => {
  setMessages("en", { files: { one: "{count} file", other: "{count} files" } });
  assert.equal(t("files", { count: 1 }), "1 file");
  assert.equal(t("files", { count: 0 }), "0 files");
});
