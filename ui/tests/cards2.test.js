import { describe, expect, test } from "vitest";
import { micHtml, monthHtml, scoresHtml, tasksHtml } from "../src/cards.js";
import { initialState, reduce } from "../src/store.js";

describe("tasks card", () => {
  test("lists open tasks with their due label and tone", () => {
    const h = tasksHtml({ tasks: [{ text: "Old chore", when: "5D LATE", tone: "late" }, { text: "Call the bank", when: "", tone: "normal" }] });
    expect(h).toContain('<span class="late">Old chore</span>');
    expect(h).toContain("Call the bank");
    expect(h.indexOf("Old chore")).toBeLessThan(h.indexOf("Call the bank"));
  });
  test("empty", () => {
    expect(tasksHtml({ tasks: [] })).toContain("No open tasks");
  });
});

describe("month card", () => {
  const month = { label: "NOVEMBER", offset: 6, days: Array.from({ length: 30 }, (_, i) => ({
    day: i + 1, kind: i + 1 === 24 ? "exam" : i + 1 === 20 ? "due" : i + 1 === 15 ? "today" : "", today: i + 1 === 15 })) };
  test("grid has weekday heads, leading blanks and one cell per day", () => {
    const h = monthHtml({ month });
    expect((h.match(/class="wd"/g) || []).length).toBe(7);
    expect((h.match(/class="blank"/g) || []).length).toBe(6);
    expect((h.match(/data-day=/g) || []).length).toBe(30);
  });
  test("exam, deadline and today are marked by class, with no inline styles", () => {
    const h = monthHtml({ month });
    expect(h).toContain('class="day exam" data-day="24"');
    expect(h).toContain('class="day due" data-day="20"');
    expect(h).toContain('class="day today" data-day="15"');
    expect(h).not.toContain("style=");
  });
  test("missing data", () => {
    expect(monthHtml({})).toContain("empty");
  });
});

describe("scores card", () => {
  test("one bar row per subject, width by class", () => {
    const h = scoresHtml({ scores: [{ subject: "DBMS", percent: 73, count: 2 }, { subject: "CN", percent: 64, count: 1 }] });
    expect(h).toContain("DBMS");
    expect(h).toContain("73%");
    expect(h).toContain('class="w7"');
    expect(h).toContain('class="w6"');
    expect(h).not.toContain("style=");
  });
  test("a weak average is toned as a warning", () => {
    expect(scoresHtml({ scores: [{ subject: "Bio", percent: 38, count: 1 }] })).toContain("late");
  });
});

describe("phone mic card", () => {
  test("shows the link and the code while the phone is not connected", () => {
    const h = micHtml({ mic_hint: { url: "https://192.168.1.3:8766", code: "274852" } });
    expect(h).toContain("https://192.168.1.3:8766");
    expect(h).toContain("274852");
  });
  test("nothing when connected or not using the phone", () => {
    expect(micHtml({ mic_hint: null })).toBe("");
    expect(micHtml({})).toBe("");
  });
});

describe("store", () => {
  test("the new cards can be highlighted", () => {
    const s = reduce(initialState(), { type: "focus", cards: ["tasks", "month", "bogus"] }, 0);
    expect(s.cards).toEqual(["tasks", "month"]);
  });
});
