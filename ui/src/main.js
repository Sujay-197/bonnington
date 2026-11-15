import { connect } from "./bridge.js";
import { createGlobe } from "./globe.js";
import { initialState, reduce } from "./store.js";
import { renderSubtitles } from "./subtitles.js";

const params = new URLSearchParams(location.search);
const port = params.get("port") || "8765";
let state = initialState();

connect(`ws://127.0.0.1:${port}`, (ev) => { state = reduce(state, ev, performance.now()); });
createGlobe(document.getElementById("globe"), () => state);

const subs = document.getElementById("subs"), user = document.getElementById("user");
(function tick() {
  const now = performance.now();
  renderSubtitles(subs, user, state, now);
  subs.style.visibility = state.lines.length ? "visible" : "hidden";
  user.style.visibility = state.lines.length ? "hidden" : "visible";
  requestAnimationFrame(tick);
})();

window.addEventListener("keydown", async (e) => {
  const tauri = window.__TAURI__;
  if (!tauri) return;
  const win = tauri.window.getCurrentWindow();
  if (e.key === "F11") await win.setFullscreen(!(await win.isFullscreen()));
  if (e.key === "Escape") await win.hide();
});
