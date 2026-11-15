import { expect, test } from "vitest";
import { visibleWords } from "../src/subtitles.js";
import { MOOD_RGB } from "../src/globe.js";

test("visibleWords reveals by offset", () => {
  const line = { text: "Britney. Again. Really.", startedAt: 1000, wordOffsetsMs: [0, 400, 900] };
  expect(visibleWords(line, 1500)).toBe("Britney. Again.");
});
test("visibleWords shows everything after the last offset", () => {
  const line = { text: "a b", startedAt: 0, wordOffsetsMs: [0, 100] };
  expect(visibleWords(line, 5000)).toBe("a b");
});
test("visibleWords with no offsets shows whole line", () => {
  expect(visibleWords({ text: "a b", startedAt: 0, wordOffsetsMs: [] }, 0)).toBe("a b");
});
test("mood table matches spec", () => {
  expect(MOOD_RGB).toEqual({
    neutral: [255, 255, 255], amused: [250, 199, 117], annoyed: [240, 90, 80],
    smug: [175, 169, 236], serious: [133, 183, 235], disappointed: [150, 150, 145],
  });
});

import { statusText } from "../src/subtitles.js";
import { initialState as init } from "../src/store.js";

test("status cue while listening and waking", () => {
  expect(statusText({ ...init(), phase: "listening" })).toBe("listening…");
  expect(statusText({ ...init(), phase: "waking" })).toBe("waking up…");
  expect(statusText({ ...init(), phase: "thinking" })).toBe("");
  expect(statusText({ ...init(), phase: "listening", userText: "hey" })).toBe("");
});
