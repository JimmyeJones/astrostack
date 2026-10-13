import { describe, expect, it } from "vitest";
import type { AutoDrizzleCost } from "./api/client";
import { autoDrizzleCostLine, formatDrizzleScale } from "./autoDrizzleNote";

const COST: AutoDrizzleCost = {
  scale: 1.5,
  drizzle_seconds: 14 * 3600,
  plain_seconds: 2 * 3600,
  basis_runs: 3,
  same_engine: true,
};

describe("autoDrizzleCostLine", () => {
  it("says how long, and what a plain stack would have taken", () => {
    // The owner's own sentence (sign-off item 19). The comparison is the point:
    // "about 14 h" alone reads as the app being slow.
    expect(autoDrizzleCostLine(COST)).toBe(
      "Drizzling ×1.5 — about 14 h (a plain stack would take about 2 h).");
  });

  it("falls back to the measured ratio when nothing of this target is timed", () => {
    // A fresh install, or a target stacked for the first time. Silence is the
    // one wrong answer: the whole point of his choice is that an automatic
    // drizzle never starts a long run without saying so.
    const line = autoDrizzleCostLine({
      ...COST, drizzle_seconds: null, plain_seconds: null, basis_runs: 0,
    });
    expect(line).toBe(
      "Drizzling ×1.5 — this will take several times longer than a normal stack.");
  });

  it("never prints half a comparison", () => {
    // The backend sends the two numbers together or not at all; if some future
    // caller sends one, the wording drops to the no-number form rather than
    // promising "about 14 h" with nothing to compare it against.
    for (const half of [{ drizzle_seconds: null }, { plain_seconds: null }]) {
      expect(autoDrizzleCostLine({ ...COST, ...half })).toContain(
        "several times longer");
    }
  });

  it("names the build when the rate came from a different one", () => {
    // Across one real upgrade the owner's identical restacks came back 8–36 %
    // slower (observer issue #933), so the caveat rides along with the number.
    const line = autoDrizzleCostLine({ ...COST, same_engine: false });
    expect(line).toContain("about 14 h");
    expect(line).toContain("a different version of AstroStack");
  });

  it("stays quiet on a job that chose no drizzle", () => {
    expect(autoDrizzleCostLine(null)).toBeNull();
    expect(autoDrizzleCostLine(undefined)).toBeNull();
  });

  it("carries the stepped-down scale the run actually chose", () => {
    expect(autoDrizzleCostLine({ ...COST, scale: 1.2 })).toContain("×1.2");
  });

  it("drops the scale rather than printing nonsense", () => {
    const line = autoDrizzleCostLine({ ...COST, scale: Number.NaN });
    expect(line).toBe("Drizzling — about 14 h (a plain stack would take about 2 h).");
  });

  it("treats a zero or negative duration as no estimate", () => {
    expect(autoDrizzleCostLine({ ...COST, drizzle_seconds: 0 })).toContain(
      "several times longer");
    expect(autoDrizzleCostLine({ ...COST, plain_seconds: -1 })).toContain(
      "several times longer");
  });
});

describe("formatDrizzleScale", () => {
  it("prints the scales the automatic path can choose", () => {
    expect(formatDrizzleScale(1.5)).toBe("1.5");
    expect(formatDrizzleScale(1.2)).toBe("1.2");
    expect(formatDrizzleScale(2)).toBe("2");
  });

  it("is empty for a scale that means nothing", () => {
    expect(formatDrizzleScale(0)).toBe("");
    expect(formatDrizzleScale(Number.NaN)).toBe("");
    expect(formatDrizzleScale(Number.POSITIVE_INFINITY)).toBe("");
  });
});
