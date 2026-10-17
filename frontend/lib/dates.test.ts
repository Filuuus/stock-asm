// Run in Mexico's time zone (see the "test" script): the bugs these guard against only show
// up west of UTC, where midnight UTC is still the previous day.
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  currentMonthISO,
  dateToISO,
  formatDay,
  formatDayShort,
  formatMonth,
  isoToDate,
  todayISO,
} from "./dates";

afterEach(() => {
  vi.useRealTimers();
});

describe("isoToDate", () => {
  it("keeps the calendar day (new Date('2026-09-24') would be the 23rd here)", () => {
    const d = isoToDate("2026-09-24");
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 8, 24]);
    expect(new Date("2026-09-24").getDate()).toBe(23); // the trap this helper exists for
  });

  it("reads a month as its first day", () => {
    const d = isoToDate("2026-09");
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 8, 1]);
  });

  it("round-trips every day of the year", () => {
    for (let d = new Date(2026, 0, 1); d.getFullYear() === 2026; d.setDate(d.getDate() + 1)) {
      const iso = dateToISO(d);
      expect(dateToISO(isoToDate(iso))).toBe(iso);
    }
  });
});

describe("today and the current month are local, not UTC", () => {
  it("is still the 15th at 7:30 pm on Oct 15 (01:30 UTC on the 16th)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-16T01:30:00Z"));
    expect(todayISO()).toBe("2026-10-15");
    expect(new Date().toISOString().slice(0, 10)).toBe("2026-10-16"); // what toISOString would have said
  });

  it("is still October on the evening of Oct 31", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-01T03:00:00Z"));
    expect(currentMonthISO()).toBe("2026-10");
  });
});

describe("formatting", () => {
  it("shows the stored day, for dates and datetimes alike", () => {
    expect(formatDay("2026-09-18")).toBe("18 sep 2026");
    expect(formatDay("2026-09-18T00:00:00Z")).toBe("18 sep 2026");
  });

  it("shows a dash when there is no date", () => {
    expect(formatDay(null)).toBe("-");
    expect(formatDay(undefined)).toBe("-");
    expect(formatDay("")).toBe("-");
  });

  it("formats short days and months in Spanish", () => {
    expect(formatDayShort("2026-10-06")).toBe("6 oct");
    expect(formatMonth("2026-09")).toBe("septiembre 2026");
  });
});
