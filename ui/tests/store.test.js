import { describe, expect, test } from "vitest";
import { initialState, reduce } from "../src/store.js";

describe("store", () => {
  test("keeps only last two subtitle lines", () => {
    let s = initialState();
    for (const id of [1, 2, 3]) s = reduce(s, { type: "subtitle_line", id, text: `L${id}`, duration_ms: 500, word_offsets_ms: [0] }, 1000);
    expect(s.lines.map(l => l.id)).toEqual([2, 3]);
  });
  test("subtitle line stamped with arrival time", () => {
    const s = reduce(initialState(), { type: "subtitle_line", id: 1, text: "Hi.", duration_ms: 300, word_offsets_ms: [0] }, 4242);
    expect(s.lines[0]).toMatchObject({ id: 1, text: "Hi.", startedAt: 4242, durationMs: 300, wordOffsetsMs: [0] });
  });
  test("unknown event ignored", () => {
    const s = initialState();
    expect(reduce(s, { type: "bogus" }, 0)).toEqual(s);
  });
  test("speaking clears user text", () => {
    const s = reduce(initialState(), { type: "user_partial", text: "hey" }, 0);
    expect(reduce(s, { type: "state", value: "speaking" }, 0).userText).toBe("");
  });
  test("user_final stamps time", () => {
    const s = reduce(initialState(), { type: "user_final", text: "what's left" }, 77);
    expect(s.userText).toBe("what's left"); expect(s.userTextAt).toBe(77);
  });
  test("clear_subtitles empties lines", () => {
    let s = reduce(initialState(), { type: "subtitle_line", id: 1, text: "a", duration_ms: 1, word_offsets_ms: [0] }, 0);
    expect(reduce(s, { type: "clear_subtitles" }, 0).lines).toEqual([]);
  });
  test("mood, phase, amplitude", () => {
    let s = reduce(initialState(), { type: "mood", value: "annoyed" }, 0);
    s = reduce(s, { type: "state", value: "thinking" }, 0);
    s = reduce(s, { type: "amplitude", value: 0.4 }, 0);
    expect([s.mood, s.phase, s.amplitude]).toEqual(["annoyed", "thinking", 0.4]);
  });
  test("unknown mood ignored", () => {
    expect(reduce(initialState(), { type: "mood", value: "furious" }, 0).mood).toBe("neutral");
  });
});

import { linesActive } from "../src/store.js";

describe("your words vs his subtitles", () => {
  const line = { type: "subtitle_line", id: 1, text: "Hm.", duration_ms: 1000, word_offsets_ms: [0] };
  test("his line is active while spoken and during the fade", () => {
    const s = reduce(initialState(), line, 5000);
    expect(linesActive(s, 5500)).toBe(true);
    expect(linesActive(s, 6500)).toBe(true);    // still fading out
  });
  test("his finished line no longer hides your words", () => {
    const s = reduce(initialState(), line, 5000);
    expect(linesActive(s, 6700)).toBe(false);
  });
  test("when you start speaking, his old lines are cleared", () => {
    let s = reduce(initialState(), line, 5000);
    s = reduce(s, { type: "user_partial", text: "am I" }, 5200);
    expect(s.lines).toEqual([]);
    expect(s.userText).toBe("am I");
  });
});
