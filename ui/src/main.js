import { connect } from "./bridge.js";
import { createGlobe } from "./globe.js";
import { initialState, linesActive, memoryNote, reduce } from "./store.js";
import { renderSubtitles } from "./subtitles.js";

const params = new URLSearchParams(location.search);
const port = params.get("port") || "8765";
let state = initialState();

connect(`ws://127.0.0.1:${port}`, (ev) => { state = reduce(state, ev, performance.now()); });
createGlobe(document.getElementById("globe"), () => state);

const subs = document.getElementById("subs"), user = document.getElementById("user");
const memory = document.getElementById("memory"), memoryText = document.getElementById("memory-text");
(function tick() {
  const now = performance.now();
  renderSubtitles(subs, user, state, now);
  const his = linesActive(state, now);
  subs.style.visibility = his ? "visible" : "hidden";
  user.style.visibility = his ? "hidden" : "visible";
  const note = memoryNote(state, now);
  if (note) memoryText.textContent = note;
  memory.classList.toggle("show", !!note);
  requestAnimationFrame(tick);
})();

window.addEventListener("keydown", async (e) => {
  const tauri = window.__TAURI__;
  if (!tauri) return;
  const win = tauri.window.getCurrentWindow();
  if (e.key === "F11") await win.setFullscreen(!(await win.isFullscreen()));
  if (e.key === "Escape") await win.hide();
});
