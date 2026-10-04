// Startseite: setzt die Module zusammen. Jedes Modul hängt seine Ereignisse beim Laden selbst an.

import "./js/album.js";
import { loadConfig } from "./js/config.js";
import { turtle } from "./js/dom.js";
import { connectJobs } from "./js/jobs.js";
import "./js/preview.js";
import "./js/settings.js";

document.querySelectorAll("[data-turtle]").forEach((slot) => slot.append(turtle(slot.dataset.turtle, { size: 120 })));

loadConfig();
connectJobs();
