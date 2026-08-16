import { describe, expect, it } from "vitest";
import {
  formatDiskSize, formatIntegration, formatMonthYear, formatNightDate,
  formatNightDayMonth, formatStampDate, isRecentNight, nightAgeDays,
} from "./format";

describe("formatIntegration", () => {
  it("formats each unit range", () => {
    expect(formatIntegration(8)).toBe("8 s");
    expect(formatIntegration(150)).toBe("3 min");
    expect(formatIntegration(8280)).toBe("2.3 h");
    expect(formatIntegration(36000)).toBe("10 h");
  });

  it("returns an em dash for zero / non-finite input", () => {
    expect(formatIntegration(0)).toBe("—");
    expect(formatIntegration(-5)).toBe("—");
    expect(formatIntegration(NaN)).toBe("—");
  });

  it("promotes a value that rounds up to a whole unit instead of printing '60 min' / '60 s'", () => {
    // 3599 s is 59.98 min — must read as ~1 h, not "60 min".
    expect(formatIntegration(3599)).toBe("1.0 h");
    // 59.9 s rounds to a whole minute, not "60 s".
    expect(formatIntegration(59.9)).toBe("1 min");
    // A genuine sub-boundary value stays in its own unit.
    expect(formatIntegration(30)).toBe("30 s");
    expect(formatIntegration(3000)).toBe("50 min");
  });
});

describe("formatMonthYear", () => {
  it("formats an ISO UTC stamp as Month Year", () => {
    expect(formatMonthYear("2026-01-15T00:00:00Z")).toBe("January 2026");
    expect(formatMonthYear("2025-12-31T23:59:59Z")).toBe("December 2025");
  });

  it("is timezone-stable (reads the stamp's own month, not the local one)", () => {
    // A late-UTC stamp must not roll into the next month via a local Date.
    expect(formatMonthYear("2026-03-01T23:30:00Z")).toBe("March 2026");
  });

  it("returns an em dash for null / empty / malformed input", () => {
    expect(formatMonthYear(null)).toBe("—");
    expect(formatMonthYear(undefined)).toBe("—");
    expect(formatMonthYear("")).toBe("—");
    expect(formatMonthYear("not-a-date")).toBe("—");
    expect(formatMonthYear("2026-13-01T00:00:00Z")).toBe("—");
  });
});

describe("formatNightDate", () => {
  it("formats a night date or UTC stamp as a friendly day-month-year", () => {
    expect(formatNightDate("2026-07-08")).toBe("8 Jul 2026");
    expect(formatNightDate("2026-07-08T22:00:00+00:00")).toBe("8 Jul 2026");
    expect(formatNightDate("2026-12-31T01:00:00+00:00")).toBe("31 Dec 2026");
  });

  it("returns an em dash for null / malformed input", () => {
    expect(formatNightDate(null)).toBe("—");
    expect(formatNightDate("nope")).toBe("—");
    expect(formatNightDate("2026-13-01T00:00:00Z")).toBe("—");
    expect(formatNightDate("2026-07-00T00:00:00Z")).toBe("—");
  });
});

describe("formatDiskSize", () => {
  it("is binary, so it agrees with the rest of the page", () => {
    // The bug this exists to stop: the server's free_gb is decimal (1e9), so
    // 23.4e9 bytes printed as "23 GB" above a headroom note saying "21 GB".
    expect(formatDiskSize(23.4e9)).toBe("22 GB");
    expect(formatDiskSize(2 * 1024 ** 3)).toBe("2.0 GB");
    expect(formatDiskSize(830 * 1024 ** 2)).toBe("830 MB");
    expect(formatDiskSize(0)).toBe("0 MB");
  });
});

describe("formatStampDate", () => {
  it("never prints the month as a number", () => {
    // The whole point: "8/16/2026" is read as the 8th of month 16 by half the
    // world, and these captions sit on the same screen as "15 Nov 2024".
    const out = formatStampDate("2026-08-16T12:00:00Z");
    expect(out).not.toBe("");
    expect(out).toContain("2026");
    expect(out).toMatch(/[A-Za-z]{3}/);          // a named month
    expect(out).not.toMatch(/\b\d{1,2}\/\d{1,2}\//);  // no 8/16/2026
  });

  it("drops the clause rather than printing Invalid Date", () => {
    expect(formatStampDate(null)).toBe("");
    expect(formatStampDate(undefined)).toBe("");
    expect(formatStampDate("")).toBe("");
    expect(formatStampDate("not-a-date")).toBe("");
  });
});

describe("nightAgeDays", () => {
  const morningAfter = new Date("2026-07-09T09:00:00Z");

  it("counts whole calendar days back to the observing night", () => {
    expect(nightAgeDays("2026-07-09", morningAfter)).toBe(0);
    expect(nightAgeDays("2026-07-08", morningAfter)).toBe(1);
    expect(nightAgeDays("2026-06-25", morningAfter)).toBe(14);
  });

  it("counts across a month and a year boundary", () => {
    expect(nightAgeDays("2026-06-30", new Date("2026-07-01T09:00:00Z"))).toBe(1);
    expect(nightAgeDays("2025-12-31", new Date("2026-01-01T09:00:00Z"))).toBe(1);
  });

  it("reads the date off a full UTC stamp too", () => {
    expect(nightAgeDays("2026-07-08T22:00:00+00:00", morningAfter)).toBe(1);
  });

  it("is null when there is no datable night", () => {
    expect(nightAgeDays(null, morningAfter)).toBeNull();
    expect(nightAgeDays("", morningAfter)).toBeNull();
    expect(nightAgeDays("nope", morningAfter)).toBeNull();
    expect(nightAgeDays("2026-13-01", morningAfter)).toBeNull();
  });
});

describe("isRecentNight", () => {
  const morningAfter = new Date("2026-07-09T09:00:00Z");

  it("is true for tonight's own session and the night just gone", () => {
    expect(isRecentNight("2026-07-09", morningAfter)).toBe(true);
    expect(isRecentNight("2026-07-08", morningAfter)).toBe(true);
  });

  it("is false once a night is older than that", () => {
    expect(isRecentNight("2026-07-07", morningAfter)).toBe(false);
    expect(isRecentNight("2026-06-25", morningAfter)).toBe(false);
  });

  it("keeps the warm wording when the night is undatable or in the future", () => {
    // Undatable → we have nothing better to say; a future stamp (clock skew)
    // must not announce a date that hasn't happened yet.
    expect(isRecentNight(null, morningAfter)).toBe(true);
    expect(isRecentNight("nope", morningAfter)).toBe(true);
    expect(isRecentNight("2026-07-20", morningAfter)).toBe(true);
  });
});

describe("formatNightDayMonth", () => {
  it("drops the year while the night is in the current year", () => {
    expect(formatNightDayMonth("2026-07-08", new Date("2026-07-23T09:00:00Z")))
      .toBe("8 Jul");
  });

  it("keeps the year once the night is not this year", () => {
    expect(formatNightDayMonth("2026-07-08", new Date("2027-01-05T09:00:00Z")))
      .toBe("8 Jul 2026");
  });

  it("is null when the night can't be dated", () => {
    expect(formatNightDayMonth(null, new Date("2026-07-23T09:00:00Z"))).toBeNull();
    expect(formatNightDayMonth("nope", new Date("2026-07-23T09:00:00Z"))).toBeNull();
  });
});
