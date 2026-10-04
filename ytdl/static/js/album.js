// Album in einem Video: Grenzen prüfen und verschieben (Tabelle, Wellenform, Player), neu erkennen, schneiden.

import { selectedFormat } from "./config.js";
import { submitWithConflicts } from "./conflicts.js";
import { coverField } from "./cover.js";
import { $, el, hideError, showError } from "./dom.js";
import { editableCell, resetButton, vaToggle } from "./editing.js";
import { formatTime, parseTime, sameValue, snapshot } from "./format.js";
import { previewUrl } from "./preview.js";
import { renderSteps, runActivity, showBusy } from "./progress.js";

let album = null; // { id, duration, peaks, tracks: [{start, artist, title}] }
const audio = $("#album-audio");
const albumCover = coverField($("#album-cover"));
const wave = $("#wave");

function albumBusy(busy, text = "Analysiere …") {
  document.querySelectorAll("#album button").forEach((b) => (b.disabled = busy));
  showBusy($("#album-busy"), busy ? text : "");
  if (busy) hideError($("#album-error"));
  else $("#album-steps").hidden = true;
}

const albumError = (err) => showError($("#album-error"), err);

function sortTracks() {
  album.tracks.sort((a, b) => a.start - b.start);
}

function trackEnd(i) {
  return i + 1 < album.tracks.length ? album.tracks[i + 1].start : album.duration;
}

const TRACK_KEYS = ["start", "artist", "title"];
const trackCopy = (track) => snapshot(track, TRACK_KEYS);

function setTracks(result, steps) {
  // Jede neue Erkennung (Analyse, Pausen, Trackliste, Scan) ist der neue Ausgangszustand für „Zurücksetzen“
  album.original.tracks = result.tracks.map(trackCopy);
  album.tracks = result.tracks.map((track) => ({ ...trackCopy(track), orig: trackCopy(track) }));
  album.source = result.source_label;
  $("#album-source").textContent = `Grenzen aus: ${result.source_label} · bitte kontrollieren`;
  if (steps) renderSteps($("#album-log-steps"), steps);
  renderAlbum();
}

$("#album-open").addEventListener("click", async () => {
  $("#preview").hidden = true;
  $("#album").hidden = false;
  $("#album-body").hidden = true;
  $("#album-source").textContent = "";
  albumBusy(true);
  try {
    const data = await runActivity("/api/album/analyze", { url: previewUrl() }, $("#album-steps"));
    album = { id: data.id, duration: data.duration, peaks: data.peaks, tracks: [], albumArtist: data.artist,
      original: { album: data.album, artist: data.artist, year: data.year || "", tracks: [] } };
    resetAlbumFields();
    albumCover.setThumbnail(data.thumbnail);
    renderHints(data.hints || []);
    audio.src = data.audio_url;
    $("#album-body").hidden = false;
    setTracks(data, data.steps);
  } catch (err) {
    albumError(err);
  } finally {
    albumBusy(false);
  }
});

function resetAlbumFields() {
  const o = album.original;
  albumCover.clear();
  showArtistCol = false;
  $("#album-va").checked = false;
  $("#album-artist").disabled = $("#album-apply").disabled = false;
  $("#album-name").value = o.album;
  $("#album-artist").value = o.artist;
  $("#album-year").value = o.year;
  $("#album-genre").value = "";
  album.albumArtist = o.artist;
}

$("#album-reset").addEventListener("click", () => {
  if (!confirm("Album-Felder, Titel und Grenzen auf das Ergebnis der Erkennung zurücksetzen?")) return;
  resetAlbumFields();
  album.tracks = album.original.tracks.map((track) => ({ ...trackCopy(track), orig: trackCopy(track) }));
  renderAlbum();
});

function renderHints(hints) {
  const box = $("#album-hints");
  box.hidden = !hints.length;
  box.replaceChildren("Weiterer Text im Bild (klicken = als Albuminterpret):",
    ...hints.map((h) => {
      return el("button", { type: "button", class: "chip", onclick: () => {
        if ($("#album-va").checked) return;
        $("#album-artist").value = h;
        setAlbumArtist(h);
      } }, h);
    }));
}

let showArtistCol = false;

/** Neuer Albuminterpret: Titel, die noch den alten Interpreten hatten, ziehen mit; abweichende bleiben. */
function setAlbumArtist(next) {
  const old = album.albumArtist;
  album.tracks.forEach((track) => { if (!track.artist || track.artist === old) track.artist = next; });
  album.albumArtist = next;
  renderAlbum();
}

$("#album-artist").addEventListener("change", () => setAlbumArtist($("#album-artist").value.trim()));

$("#album-apply").addEventListener("click", () => {
  const artist = $("#album-artist").value.trim();
  album.tracks.forEach((track) => (track.artist = artist));
  album.albumArtist = artist;
  renderAlbum();
});

// Interpreten der Titel bleiben bei „Verschiedene Interpreten“ einzeln erhalten
vaToggle($("#album-va"), $("#album-artist"), [$("#album-apply")], (artist) => {
  album.albumArtist = artist;
  renderAlbum();
});

$("#album-artist-col").addEventListener("click", () => {
  showArtistCol = !showArtistCol;
  renderAlbum();
});

function updateArtistColumn() {
  const va = $("#album-va").checked;
  const uniform = album.tracks.every((track) => track.artist === album.albumArtist);
  const hide = !va && !showArtistCol && uniform;
  $("#album-table").classList.toggle("hide-artist", hide);
  const toggle = $("#album-artist-col");
  toggle.hidden = va || !uniform;
  toggle.textContent = showArtistCol ? "Interpret-Spalte ausblenden" : "Interpret pro Titel bearbeiten";
}

function renderAlbum() {
  sortTracks();
  updateArtistColumn();
  const playing = currentTrackIndex();
  $("#album-tracks").replaceChildren(...album.tracks.map((track, i) => {
    const start = el("input", { value: formatTime(track.start, { tenths: true }), onchange: () => {
      const v = parseTime(start.value);
      if (v != null && v >= 0 && v < album.duration) track.start = v;
      renderAlbum();
    } });
    const startCell = el("td", { class: "time" }, start);
    startCell.classList.toggle("changed", !!track.orig && !sameValue(track.start, track.orig.start));
    const reset = resetButton(track, TRACK_KEYS, renderAlbum, "secondary");
    const action = (label, title, onclick) => el("button", { type: "button", class: "secondary", title, onclick }, label);
    return el("tr", { class: i === playing ? "playing" : "" },
      el("td", { class: "dur" }, String(i + 1)),
      startCell,
      el("td", { class: "dur" }, formatTime(trackEnd(i) - track.start)),
      editableCell(track, "artist", { onInput: reset.refresh }), editableCell(track, "title", { onInput: reset.refresh }),
      el("td", { class: "actions" },
        action("▶", "Ab Start abspielen", () => { audio.currentTime = track.start; audio.play(); }),
        action("⇤ hier", "Start = aktuelle Abspielposition", () => { track.start = audio.currentTime; renderAlbum(); }),
        reset,
        action("✕", "Grenze entfernen (mit vorherigem Titel zusammenfassen)", () => {
          album.tracks.splice(i, 1);
          renderAlbum();
        })));
  }));
  drawWave();
}

function currentTrackIndex() {
  if (!album) return -1;
  let idx = -1;
  album.tracks.forEach((track, i) => { if (audio.currentTime >= track.start) idx = i; });
  return idx;
}

function drawWave() {
  if (!album) return;
  const dpr = window.devicePixelRatio || 1;
  const w = wave.clientWidth, h = wave.clientHeight;
  wave.width = w * dpr; wave.height = h * dpr;
  const ctx = wave.getContext("2d");
  ctx.scale(dpr, dpr);
  const { accent, muted, text } = waveColors();

  ctx.fillStyle = muted;
  const n = album.peaks.length;
  for (let x = 0; x < w; x++) {
    const v = album.peaks[Math.floor((x / w) * n)] || 0;
    const bar = Math.max(1, v * (h - 22));
    ctx.fillRect(x, (h + 14 - bar) / 2, 1, bar);
  }
  ctx.font = "11px system-ui, sans-serif";
  album.tracks.forEach((track, i) => {
    const x = (track.start / album.duration) * w;
    ctx.fillStyle = accent;
    ctx.fillRect(x - 1, 0, 2, h);
    ctx.fillText(String(i + 1), x + 3, 11);
  });
  const px = (audio.currentTime / album.duration) * w;
  ctx.fillStyle = text;
  ctx.fillRect(px - 0.5, 0, 1, h);
}

// Farben aus dem Theme – einmal lesen und erst bei einem Wechsel hell/dunkel neu (drawWave läuft bei jedem timeupdate)
let colors = null;
function waveColors() {
  if (!colors) {
    const css = getComputedStyle(document.documentElement);
    const v = (name) => css.getPropertyValue(name).trim();
    colors = { accent: v("--frame"), muted: v("--muted"), text: v("--text") };
  }
  return colors;
}
window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => { colors = null; drawWave(); });

let dragging = null;
function waveTime(event) {
  const rect = wave.getBoundingClientRect();
  return Math.min(album.duration, Math.max(0, ((event.clientX - rect.left) / rect.width) * album.duration));
}
wave.addEventListener("pointerdown", (event) => {
  if (!album) return;
  const rect = wave.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const hit = album.tracks.findIndex((track, i) => i > 0 && Math.abs((track.start / album.duration) * rect.width - x) < 6);
  if (hit > 0) {
    dragging = album.tracks[hit];
    wave.setPointerCapture(event.pointerId);
  } else {
    audio.currentTime = waveTime(event);
    drawWave();
  }
});
wave.addEventListener("pointermove", (event) => {
  if (!dragging) return;
  dragging.start = waveTime(event);
  drawWave();
});
wave.addEventListener("pointerup", () => {
  if (!dragging) return;
  audio.currentTime = Math.max(0, dragging.start - 3);
  dragging = null;
  renderAlbum();
});

let lastPlaying = -1;
audio.addEventListener("timeupdate", () => {
  drawWave();
  const idx = currentTrackIndex();
  if (idx !== lastPlaying) {
    lastPlaying = idx;
    document.querySelectorAll("#album-tracks tr").forEach((tr, i) => tr.classList.toggle("playing", i === idx));
  }
});
window.addEventListener("resize", drawWave);

$("#album-add").addEventListener("click", () => {
  const artist = $("#album-va").checked ? "" : $("#album-artist").value;
  album.tracks.push({ start: audio.currentTime, artist, title: "" });
  renderAlbum();
});

async function albumAction(path, body) {
  albumBusy(true);
  const box = $("#album-steps");
  box.scrollIntoView({ block: "nearest", behavior: "smooth" });
  try {
    const result = await runActivity(`/api/album/${album.id}/${path}`,
      { ...body, artist: $("#album-artist").value }, box);
    setTracks(result, result.steps);
  } catch (err) {
    albumError(err);
  } finally {
    albumBusy(false);
  }
}

$("#det-run").addEventListener("click", () => {
  const count = $("#det-count").value ? Number($("#det-count").value) : null;
  albumAction("detect", { count, min_pause: Number($("#det-pause").value), sensitivity: Number($("#det-sens").value) });
});
$("#det-text-run").addEventListener("click", () => albumAction("text", { text: $("#det-text").value }));
$("#det-scan").addEventListener("click", () => albumAction("scan", {}));

$("#album-cut").addEventListener("click", async () => {
  albumBusy(true, "Prüfe, ob schon etwas da ist …");
  try {
    sortTracks();
    const body = {
      album: $("#album-name").value, album_artist: $("#album-artist").value,
      year: $("#album-year").value, genre: $("#album-genre").value,
      audio_format: selectedFormat(), ...albumCover.value(), boundary_source: album.source || "",
      tracks: album.tracks.map(({ orig, ...track }) => track),
    };
    const base = `/api/album/${album.id}`;
    if (!(await submitWithConflicts(`${base}/conflicts`, `${base}/jobs`, body, album.tracks.length))) return;
    audio.pause();
    $("#album").hidden = true;
    $("#url").value = "";
  } catch (err) {
    albumError(err);
  } finally {
    albumBusy(false);
  }
});
