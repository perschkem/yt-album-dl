// Kleine DOM-Helfer für beide Seiten.

export const $ = (sel) => document.querySelector(sel);

/** Element bauen: Attribute bzw. Eigenschaften (auch onclick …), Kinder; null/undefined/"" werden ausgelassen. */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k in node) node[k] = v;
    else node.setAttribute(k, v);
  }
  node.append(...children.filter((c) => c != null && c !== ""));
  return node;
}

/** Button, der während der (async) Aktion gesperrt ist; Fehler erscheinen als Hinweis. */
export function button(label, onClick, { cls = "secondary small-btn", title = "" } = {}) {
  const b = el("button", { type: "button", class: cls, title }, label);
  b.addEventListener("click", async () => {
    b.disabled = true;
    try { await onClick(); } catch (err) { alert(err.message); } finally { b.disabled = false; }
  });
  return b;
}

/** Fehlermeldung in einem Absatz anzeigen (err: Error oder Text) bzw. ausblenden. */
export function showError(box, err) {
  box.textContent = typeof err === "string" ? err : err.message;
  box.hidden = false;
}

export function hideError(box) {
  box.hidden = true;
}

// ---------- Schildkröten ----------
// Fertige Bilder je Situation (DESIGN.md). Fehlende kommen nach und nach – bis dahin der Pixel-Platzhalter.
export const TURTLES = {
  pruefen: { src: "img/turtles/pruefen.webp", round: true },
  downloads: { src: "img/turtles/downloads.webp", round: true },
};
export const TURTLE_PLACEHOLDER = "img/turtles/platzhalter.svg";

export function turtle(situation, { size = 64, walking = false, alt = "" } = {}) {
  const known = TURTLES[situation];
  const img = el("img", { src: known ? known.src : TURTLE_PLACEHOLDER, alt, width: size,
    height: known ? size : Math.round(size * 9 / 16), class: "turtle" });
  if (known?.round) img.classList.add("round");
  if (walking) img.classList.add("walking");
  return img;
}

/** Leere Liste mit kleiner Schildkröte. */
export const emptyState = (text, situation = "leer") =>
  el("div", { class: "empty" }, turtle(situation, { size: 72 }), el("span", {}, text));
