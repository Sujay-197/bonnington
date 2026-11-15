// Subtitle rendering: reveal words of each line in sync with the voice.
export function visibleWords(line, nowMs) {
  const words = line.text.split(/\s+/).filter(Boolean);
  const offs = line.wordOffsetsMs || [];
  if (offs.length === 0) return words.join(" ");
  const elapsed = nowMs - line.startedAt;
  let n = 0;
  while (n < words.length && (n >= offs.length || offs[n] <= elapsed)) n++;
  return words.slice(0, n).join(" ");
}

const FADE_MS = 600;
const USER_FADE_AFTER_MS = 1500;

export function renderSubtitles(el, userEl, state, nowMs) {
  const html = state.lines.map((line, i) => {
    const older = i < state.lines.length - 1;
    const ended = nowMs - line.startedAt - line.durationMs;
    const fade = older || ended > 0 ? Math.max(0, 1 - Math.max(ended, older ? FADE_MS : 0) / FADE_MS) : 1;
    const opacity = older ? Math.min(fade, 0.45) : fade;
    return `<div style="opacity:${opacity.toFixed(2)};transition:opacity .2s">${escapeHtml(visibleWords(line, nowMs))}</div>`;
  }).join("");
  if (el.innerHTML !== html) el.innerHTML = html;
  let userOpacity = state.userText || statusText(state) ? 1 : 0;
  if (state.userTextAt != null) userOpacity = Math.max(0, 1 - (nowMs - state.userTextAt - USER_FADE_AFTER_MS) / FADE_MS);
  userEl.textContent = state.userText || statusText(state);
  userEl.style.opacity = Math.min(1, userOpacity).toFixed(2);
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// A quiet cue so you can tell he's listening before you've said anything.
export function statusText(state) {
  if (state.userText) return "";
  if (state.phase === "waking") return "waking up…";
  if (state.phase === "listening") return "listening…";
  return "";
}
