// Pure reducer: backend events -> UI state. `now` is passed in so it stays testable.
const MOODS = ["neutral", "amused", "annoyed", "smug", "serious", "disappointed"];
const PHASES = ["idle", "listening", "thinking", "speaking", "waking"];

export function initialState() {
  return { phase: "idle", mood: "neutral", userText: "", userTextAt: null, lines: [], amplitude: 0, memory: null };
}

export function reduce(state, ev, now) {
  switch (ev.type) {
    case "state":
      if (!PHASES.includes(ev.value)) return state;
      return { ...state, phase: ev.value, userText: ev.value === "speaking" ? "" : state.userText };
    case "mood":
      return MOODS.includes(ev.value) ? { ...state, mood: ev.value } : state;
    case "user_partial":
      return { ...state, userText: ev.text, userTextAt: null, lines: [] };
    case "user_final":
      return { ...state, userText: ev.text, userTextAt: now };
    case "subtitle_line": {
      const line = { id: ev.id, text: ev.text, startedAt: now, durationMs: ev.duration_ms, wordOffsetsMs: ev.word_offsets_ms || [] };
      return { ...state, lines: [...state.lines, line].slice(-2) };
    }
    case "clear_subtitles":
      return { ...state, lines: [] };
    case "memory":
      return { ...state, memory: { text: String(ev.text || ""), at: now } };
    case "amplitude":
      return { ...state, amplitude: Number(ev.value) || 0 };
    default:
      return state;
  }
}

const FADE_MS = 600;

// True while one of his subtitle lines is still being spoken or fading out.
export function linesActive(state, now) {
  return state.lines.some(l => now < l.startedAt + l.durationMs + FADE_MS);
}

const MEMORY_NOTE_MS = 5000;

// The "memory updated" note: what he just changed, shown briefly.
export function memoryNote(state, now) {
  const m = state.memory;
  return m && now - m.at < MEMORY_NOTE_MS ? m.text : "";
}
