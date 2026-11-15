import { connect } from "./bridge.js";
import { countsHtml, focusHtml, nextHtml, projectsHtml, scoresHtml, statusRight, weekHtml } from "./cards.js";
import { createGlobe } from "./globe.js";
import { initialState, linesActive, memoryNote, reduce } from "./store.js";
import { renderSubtitles } from "./subtitles.js";

const params = new URLSearchParams(location.search);
const port = params.get("port") || "8765";
const $ = (id) => document.getElementById(id);
let state = initialState();

const win = () => (window.__TAURI__ ? window.__TAURI__.window.getCurrentWindow() : null);

async function reveal() {            // a summons brings the window back if it was hidden or minimised
  const w = win();
  if (!w) return;
  try { await w.show(); await w.unminimize(); } catch { /* window controls are best-effort */ }
}

connect(`ws://127.0.0.1:${port}`, (ev) => {
  const before = state.phase;
  state = reduce(state, ev, performance.now());
  if (ev.type === "show_window") reveal();
  if (ev.type === "state" && before === "idle" && (state.phase === "waking" || state.phase === "listening")) reveal();
});
createGlobe($("globe"), () => state);

// --- cards: re-rendered only when their data or highlight actually changes ---------------------------
const BUILDERS = { week: weekHtml, counts: countsHtml, scores: scoresHtml, next: nextHtml, projects: projectsHtml, focus: focusHtml };
let shownDash = null, shownCards = "", shownStatus = null;
function renderCards() {
  if (state.dash !== shownDash) {
    shownDash = state.dash;
    const d = shownDash || {};
    for (const [name, build] of Object.entries(BUILDERS)) {
      $(`card-${name}`).querySelector(".body").innerHTML = shownDash ? build(d) : `<div class="empty">Waiting for data…</div>`;
    }
    $("t-brit").textContent = shownDash ? `BRITNEY ${d.britney}` : "";
    $("b-left").textContent = (d.status && d.status.left) || "";
  }
  const status = statusRight(state.dash, state.phase);
  if (status !== shownStatus) { shownStatus = status; $("b-right").textContent = status; }
  const key = state.cards.join(",");
  if (key !== shownCards) {
    shownCards = key;
    for (const name of Object.keys(BUILDERS)) $(`card-${name}`).classList.toggle("on", state.cards.includes(name));
  }
}

function renderClock() {
  const now = new Date();
  const date = (state.dash && state.dash.date) || "";
  $("t-date").textContent = `${date} · ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}
setInterval(renderClock, 1000);

const subs = $("subs"), user = $("user"), memory = $("memory"), memoryText = $("memory-text");
(function tick() {
  const now = performance.now();
  renderSubtitles(subs, user, state, now);
  const his = linesActive(state, now);
  subs.style.visibility = his ? "visible" : "hidden";
  user.style.visibility = his ? "hidden" : "visible";
  const note = memoryNote(state, now);
  if (note) memoryText.textContent = note;
  memory.classList.toggle("show", !!note);
  renderCards();
  requestAnimationFrame(tick);
})();

// --- window controls ------------------------------------------------------------------------------------
async function toggleFullscreen() {
  const w = win();
  if (w) await w.setFullscreen(!(await w.isFullscreen()));
}
$("w-min").onclick = () => win() && win().minimize();
$("w-full").onclick = toggleFullscreen;
$("w-hide").onclick = () => win() && win().hide();
window.addEventListener("keydown", (e) => {
  if (e.key === "F11") { e.preventDefault(); toggleFullscreen(); }
  if (e.key === "Escape") win() && win().isFullscreen().then((full) => full && win().setFullscreen(false));
});
