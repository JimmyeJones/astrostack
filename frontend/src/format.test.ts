import { describe, expect, it } from "vitest";
import { formatIntegration, formatMonthYear } from "./format";

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
