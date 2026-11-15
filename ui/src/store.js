// Pure reducer: backend events -> UI state. `now` is passed in so it stays testable.
const MOODS = ["neutral", "amused", "annoyed", "smug", "serious", "disappointed"];
const PHASES = ["idle", "listening", "thinking", "speaking", "waking"];

export function initialState() {
  return { phase: "idle", mood: "neutral", userText: "", userTextAt: null, lines: [], amplitude: 0 };
}

export function reduce(state, ev, now) {
  switch (ev.type) {
    case "state":
      if (!PHASES.includes(ev.value)) return state;
      return { ...state, phase: ev.value, userText: ev.value === "speaking" ? "" : state.userText };
    case "mood":
      return MOODS.includes(ev.value) ? { ...state, mood: ev.value } : state;
    case "user_partial":
      return { ...state, userText: ev.text, userTextAt: null };
    case "user_final":
      return { ...state, userText: ev.text, userTextAt: now };
    case "subtitle_line": {
      const line = { id: ev.id, text: ev.text, startedAt: now, durationMs: ev.duration_ms, wordOffsetsMs: ev.word_offsets_ms || [] };
      return { ...state, lines: [...state.lines, line].slice(-2) };
    }
    case "clear_subtitles":
      return { ...state, lines: [] };
    case "amplitude":
      return { ...state, amplitude: Number(ev.value) || 0 };
    default:
      return state;
  }
}
