// Aufrufe der eigenen API und Live-Updates (Server-Sent Events).

import { t } from "./i18n.js";

/** JSON-Anfrage. Ohne body/method GET, sonst POST (oder `method`). Fehler werfen eine Error mit lesbarer Meldung;
 *  err.fields = Meldungen je Formularfeld, err.missingFolder = kein Zielordner eingestellt. */
export async function api(path, body, method) {
  const res = await fetch(path, body || method ? {
    method: method || "POST", headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  } : undefined);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    // detail ist ein Text, ein Objekt {message, fields} (Einstellungen) oder eine Liste (Validierung, 422)
    const message = typeof detail === "string" ? detail : detail?.message;
    const err = new Error(message || t("errors.http", { status: res.status }));
    err.fields = (detail && !Array.isArray(detail) && typeof detail === "object" && detail.fields) || {};
    err.missingFolder = !!data.missing_folder;
    throw err;
  }
  return data;
}

/** Abonniert einen SSE-Endpunkt; onData bekommt jede Nachricht als Objekt. EventSource verbindet sich bei
 *  Abbruch selbst neu. Liefert die EventSource (zum Schließen). */
export function subscribe(url, onData, onError) {
  const source = new EventSource(url);
  source.onmessage = (event) => onData(JSON.parse(event.data));
  if (onError) source.onerror = () => onError(source);
  return source;
}
