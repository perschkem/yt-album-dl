// Lädt in Node-Tests das echte Wörterbuch aus ytdl/locales (im Browser kommt es von /api/i18n).
import { readFileSync } from "node:fs";

import { setMessages } from "../../ytdl/static/js/i18n.js";

export function useLanguage(lang) {
  const url = new URL(`../../ytdl/locales/${lang}.json`, import.meta.url);
  setMessages(lang, JSON.parse(readFileSync(url, "utf-8")));
}

useLanguage("de");
