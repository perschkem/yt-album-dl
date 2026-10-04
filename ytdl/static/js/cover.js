// Cover-Feld: YouTube-Vorschaubild oder eigene URL mit Prüfung.

import { api } from "./api.js";
import { t } from "./i18n.js";

/** Cover-Feld: „Vorschaubild“ (Standard, schwarze Ränder werden entfernt) oder „Eigene URL“ mit Prüfung.
 *  Liefert {value(), clear(), setThumbnail(src, note)}. Bei eigener URL wird immer der Feldinhalt gesendet –
 *  die Prüfung ist nur Rückmeldung, der Server prüft beim Download selbst und nimmt sonst das Vorschaubild. */
export function coverField(root) {
  const input = root.querySelector("input[type=url]");
  const crop = root.querySelector(".cover-crop");
  const img = root.querySelector(".cover-preview");
  const msg = root.querySelector(".cover-msg");
  const note = root.querySelector(".cover-thumb-note");
  const urlPart = root.querySelector(".cover-url-part");
  const modes = root.querySelectorAll(".cover-mode input");
  let thumbSrc = "", thumbNote = "";
  const mode = () => root.querySelector(".cover-mode input:checked").value;
  const show = (text, isError = false) => { msg.textContent = text; msg.classList.toggle("error", isError); };

  function showThumbnail() {
    img.hidden = !thumbSrc;
    if (thumbSrc) img.src = `/api/cover/thumbnail?src=${encodeURIComponent(thumbSrc)}`;
    note.textContent = thumbNote || t("cover_field.thumbnail_note");
  }

  async function checkUrl() {
    const url = input.value.trim();
    img.hidden = true;
    if (!url) return show("");
    show(t("cover_field.checking"));
    try {
      const info = await api("/api/cover/check", { url });
      if (input.value.trim() !== url || mode() !== "url") return; // inzwischen geändert
      img.src = url;
      img.hidden = false;
      show([t("cover_field.size", info), info.square ? "" : t("cover_field.not_square")].filter(Boolean).join(" · "));
    } catch (err) {
      show(t("cover_field.keeps_thumbnail", { error: err.message }), true);
    }
  }

  function applyMode() {
    const isUrl = mode() === "url";
    urlPart.hidden = !isUrl;
    note.hidden = isUrl;
    if (isUrl) checkUrl(); else showThumbnail();
  }

  img.addEventListener("error", () => { if (mode() === "thumb") img.hidden = true; });
  modes.forEach((r) => r.addEventListener("change", applyMode));
  input.addEventListener("change", checkUrl);
  return {
    value: () => mode() === "url"
      ? { cover_url: input.value.trim(), cover_crop: crop.checked }
      : { cover_url: "", cover_crop: false },
    clear: () => {
      input.value = ""; crop.checked = false; show("");
      root.querySelector(".cover-mode input[value=thumb]").checked = true;
      applyMode();
    },
    setThumbnail: (src, text = "") => { thumbSrc = src || ""; thumbNote = text; if (mode() === "thumb") showThumbnail(); },
  };
}
