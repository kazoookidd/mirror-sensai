import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  dayGroup, fileType, formatDecimal, formatSize, formatTokens, historyDate, parseUtc, plainText,
} from "./format.js";

describe("dates", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 9, 26, 12, 0));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("reads the UTC timestamps written by SQLite", () => {
    expect(parseUtc("2026-10-26 09:30:00").toISOString()).toBe("2026-10-26T09:30:00.000Z");
  });

  it("groups conversations by day", () => {
    expect(dayGroup(new Date(2026, 9, 26, 8))).toBe("Today");
    expect(dayGroup(new Date(2026, 9, 25, 23))).toBe("Yesterday");
    expect(dayGroup(new Date(2026, 9, 21))).toBe("Earlier this week");
    expect(dayGroup(new Date(2026, 9, 10))).toBe("Older");
  });

  it("shows the time for recent chats and the date for older ones", () => {
    expect(historyDate(new Date(2026, 9, 26, 8, 5))).toBe("08:05");
    expect(historyDate(new Date(2026, 9, 25, 15, 2))).toBe("15:02");
    expect(historyDate(new Date(2026, 9, 19))).toMatch(/^[A-Z][a-z]{2}, Oct 19$/);
  });
});

describe("numbers", () => {
  it("formats file sizes", () => {
    expect(formatSize(10)).toBe("1 KB");
    expect(formatSize(2048)).toBe("2 KB");
    expect(formatSize(1.5 * 1024 * 1024)).toBe("1.5 MB");
  });

  it("formats token counts and decimals", () => {
    expect(formatTokens(400)).toBe("0.4k");
    expect(formatTokens(4000)).toBe("4k");
    expect(formatDecimal(0.75)).toBe("0.8");
  });
});

describe("text", () => {
  it("names file types", () => {
    expect(fileType("accord.PDF")).toBe("PDF");
    expect(fileType("loi.md")).toBe("Markdown");
    expect(fileType("notes.docx")).toBe("DOCX");
  });

  it("strips Markdown for previews", () => {
    expect(plainText("# Title\n**Bold** and `code`")).toBe("Title Bold and code");
  });
});
