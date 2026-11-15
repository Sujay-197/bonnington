import { describe, expect, test } from "vitest";
import { countsHtml, focusHtml, nextHtml, projectsHtml, scoresHtml, weekHtml } from "../src/cards.js";
import { initialState, reduce } from "../src/store.js";

const D = {
  date: "SUN 15 NOV", time: "23:40", britney: 214,
  week: [{ text: "Bio: Assignment 2", when: "3D LATE", tone: "late" }, { text: "CN: Lab report 3", when: "FRI · 5D", tone: "soon" }],
  later: [{ text: "DBMS: Midterm 2 09:00", when: "TUE 24 · 9D", tone: "normal" }],
  next: { text: "CN: Lab report 3", when: "IN 5 DAYS" },
  counts: { exams: 1, tasks: 2, late: 1 },
  scores: [{ subject: "DBMS", percent: 73, count: 2 }, { subject: "CN", percent: 64, count: 1 }],
  projects: { live: 3, idle: 2, done: 2, hold: 0, rows: [{ name: "medrag", note: "5D IDLE", tone: "soon" }] },
  focus: { name: "das_v0", rows: [["main", "TODAY"], ["Init thought process", "TODAY"]] },
  status: { left: "VAULT 3 DATED", right: "MIC PHONE · MODELS LOADED" },
};

describe("store", () => {
  test("dashboard event replaces the data", () => {
    const s = reduce(initialState(), { type: "dashboard", data: D }, 0);
    expect(s.dash.britney).toBe(214);
  });
  test("focus event sets highlighted cards; unknown cards are dropped", () => {
    const s = reduce(initialState(), { type: "focus", cards: ["week", "bogus", "next"] }, 0);
    expect(s.cards).toEqual(["week", "next"]);
    expect(reduce(s, { type: "focus", cards: [] }, 0).cards).toEqual([]);
  });
  test("starts with no data and nothing highlighted", () => {
    expect(initialState().dash).toBe(null);
    expect(initialState().cards).toEqual([]);
  });
});

describe("cards", () => {
  test("week lists near items with tone, then later ones", () => {
    const h = weekHtml(D);
    expect(h).toContain('<span class="late">Bio: Assignment 2</span>');
    expect(h).toContain('<span class="soon">FRI · 5D</span>');
    expect(h.indexOf("CN: Lab report 3")).toBeLessThan(h.indexOf("DBMS: Midterm 2 09:00"));
  });
  test("week says so when there is nothing", () => {
    expect(weekHtml({ ...D, week: [], later: [] })).toContain("Nothing dated");
  });
  test("counts", () => {
    const h = countsHtml(D);
    expect(h).toContain("<b>1</b><span>EXAM</span>");
    expect(h).toContain("<b>2</b><span>TASKS</span>");
    expect(h).toContain("<b>1</b><span>LATE</span>");
  });
  test("scores show the latest subject large and the others small", () => {
    const h = scoresHtml(D);
    expect(h).toContain("73%");
    expect(h).toContain("DBMS");
    expect(h).toContain("CN 64%");
    expect(scoresHtml({ ...D, scores: [] })).toContain("No scores yet");
  });
  test("next up", () => {
    expect(nextHtml(D)).toContain("CN: Lab report 3");
    expect(nextHtml(D)).toContain("IN 5 DAYS");
    expect(nextHtml({ ...D, next: null })).toContain("Nothing scheduled");
  });
  test("projects show bars sized by count and the idle rows", () => {
    const h = projectsHtml(D);
    expect(h).toContain("3 LIVE");
    expect(h).toContain("2 IDLE");
    expect(h).toContain("2 DONE");
    expect(h).toContain("height:100%");
    expect(h).toContain("medrag");
    expect(h).not.toContain("HOLD");            // no on-hold bar when there are none
  });
  test("focus shows the project and its rows", () => {
    const h = focusHtml(D);
    expect(h).toContain("das_v0");
    expect(h).toContain("Init thought process");
    expect(focusHtml({ ...D, focus: null })).toContain("No project");
  });
  test("text from the vault is escaped", () => {
    const h = weekHtml({ ...D, week: [{ text: "<img src=x onerror=alert(1)>", when: "TODAY", tone: "soon" }], later: [] });
    expect(h).not.toContain("<img");
    expect(h).toContain("&lt;img");
  });
});
