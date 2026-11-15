// Pure HTML builders for the dashboard cards. Everything shown comes from the backend's `dashboard` event.

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const row = (left, right, tone = "") =>
  `<div class="row"><span class="${tone}">${esc(left)}</span><span class="${tone || "mu"}">${esc(right)}</span></div>`;

export function weekHtml(d) {
  const near = d.week || [], later = d.later || [];
  if (!near.length && !later.length) return `<div class="empty">Nothing dated. Suspiciously peaceful.</div>`;
  let h = near.map(i => row(i.text, i.when, i.tone === "normal" ? "" : i.tone)).join("");
  if (!near.length) h = `<div class="empty">Nothing in the next 7 days.</div>`;
  if (later.length) h += `<div class="sublab">LATER</div>` + later.map(i => row(i.text, i.when)).join("");
  return h;
}

export function countsHtml(d) {
  const c = d.counts || { exams: 0, tasks: 0, late: 0 };
  return `<div class="stat">` +
    `<div><b>${c.exams}</b><span>${c.exams === 1 ? "EXAM" : "EXAMS"}</span></div>` +
    `<div class="ok"><b>${c.tasks}</b><span>TASKS</span></div>` +
    `<div class="${c.late ? "bad" : ""}"><b>${c.late}</b><span>LATE</span></div></div>`;
}

export function scoresHtml(d) {
  const s = d.scores || [];
  if (!s.length) return `<div class="empty">No scores yet.</div>`;
  const rest = s.slice(1, 4).map(x => `${esc(x.subject)} ${x.percent}%`).join(" · ");
  return `<div class="big">${s[0].percent}% <small>${esc(s[0].subject)}${rest ? " · " + rest : ""}</small></div>`;
}

export function nextHtml(d) {
  if (!d.next) return { when: "", html: `<div class="empty">Nothing scheduled.</div>` }.html;
  return `<div class="big mid">${esc(d.next.text)}</div><div class="when">${esc(d.next.when)}</div>`;
}

export function projectsHtml(d) {
  const p = d.projects || { live: 0, idle: 0, done: 0, hold: 0, rows: [] };
  const groups = [["LIVE", p.live, "ok"], ["IDLE", p.idle, "warn"], ["HOLD", p.hold, "dim"], ["DONE", p.done, "dim"]]
    .filter(g => g[1] > 0);
  const max = Math.max(1, ...groups.map(g => g[1]));
  const bars = groups.map(([name, n, cls]) =>
    `<div class="${cls} h${Math.max(1, Math.round(10 * n / max))}"><span>${n} ${name}</span></div>`).join("");
  const rows = (p.rows || []).map(r => row(r.name, r.note, r.tone === "muted" ? "mu" : r.tone)).join("");
  if (!groups.length) return `<div class="empty">No coding projects found.</div>`;
  return `<div class="bars">${bars}</div>${rows}`;
}

export function focusHtml(d) {
  const f = d.focus;
  if (!f) return `<div class="empty">No project in focus.</div>`;
  return `<div class="big mid">${esc(f.name)}</div>` + (f.rows || []).map(r => row(r[0], r[1], "mu")).join("");
}

const PHASE_LABEL = { idle: "IDLE", waking: "WAKING UP", listening: "LISTENING", thinking: "THINKING", speaking: "RESPONDING" };

// Bottom-right readout: where the mic is, whether the models are loaded, and what he is doing right now.
export function statusRight(d, phase) {
  const base = (d && d.status && d.status.right) || "";
  const now = PHASE_LABEL[phase] || "IDLE";
  return base ? `${base} · ${now}` : now;
}
