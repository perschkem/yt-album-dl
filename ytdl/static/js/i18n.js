// Übersetzungen der Oberfläche. Das Wörterbuch kommt vom Server (/api/i18n, dieselben Dateien wie im Backend:
// ytdl/locales/<sprache>.json). Module, die t() brauchen, importieren dieses Modul – durch das await unten laufen sie
// erst, wenn das Wörterbuch da ist.

let lang = "de";
let messages = {};

/** Wörterbuch setzen (beim Laden der Seite; in Tests direkt). */
export function setMessages(language, catalog) {
  lang = language;
  messages = catalog;
}

export const language = () => lang;

/** Gibt es einen Text zu `key`? (z.B. für gespeicherte Codes, die früher Klartext waren) */
export const has = (key) => key in messages;

/** Text zu `key`; Platzhalter {name} aus params, Mehrzahl über params.count. Unbekannt → der Schlüssel selbst. */
export function t(key, params = {}) {
  let value = messages[key];
  if (value == null) return key;
  if (typeof value === "object") value = value[new Intl.PluralRules(lang).select(params.count ?? 0)] ?? value.other;
  return value.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

/** Feste Texte im HTML übersetzen: data-i18n (Text), data-i18n-html (Text mit eigenem Markup aus dem Wörterbuch),
 *  data-i18n-title / -placeholder / -aria-label (Attribute). */
export function translatePage(root = document) {
  for (const node of root.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of root.querySelectorAll("[data-i18n-html]")) node.innerHTML = t(node.dataset.i18nHtml);
  for (const [attr, data] of [["title", "i18nTitle"], ["placeholder", "i18nPlaceholder"], ["aria-label", "i18nAriaLabel"]]) {
    for (const node of root.querySelectorAll(`[data-i18n-${attr}]`)) node.setAttribute(attr, t(node.dataset[data]));
  }
}

if (typeof document !== "undefined") {
  try {
    const data = await (await fetch("/api/i18n")).json();
    setMessages(data.language, data.messages);
  } catch {
    // ohne Wörterbuch erscheinen die Schlüssel – die Seite bleibt bedienbar
  }
  document.documentElement.lang = lang;
  translatePage();
}
