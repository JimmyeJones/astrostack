import { describe, it, expect } from "vitest";
import {
  integrationTrend,
  MIN_TIME_RATIO,
} from "./integrationTrend";

// Minimal run shape: the helper only reads integration time + measured noise σ.
const run = (t_s: number | null, sigma: number | null) => ({
  total_exposure_s: t_s,
  noise_sigma: sigma,
});

const HOUR = 3600;

describe("integrationTrend", () => {
  it("returns null without enough measured points", () => {
    expect(integrationTrend(null)).toBeNull();
    expect(integrationTrend([])).toBeNull();
    expect(integrationTrend([run(HOUR, 1.0)])).toBeNull();
    // Two runs but only one measures a σ → not enough.
    expect(integrationTrend([run(HOUR, 1.0), run(2 * HOUR, null)])).toBeNull();
  });

  it("returns null when the two stacks don't span a real integration increase", () => {
    // ratio 1.4 < MIN_TIME_RATIO (1.5) → can't read a trend.
    expect(integrationTrend([run(HOUR, 1.0), run(1.4 * HOUR, 0.9)])).toBeNull();
    expect(MIN_TIME_RATIO).toBe(1.5);
  });

  it("calls a stack that tracks the ideal √t 'improving'", () => {
    // Time doubles, σ falls by 1/√2 ≈ 0.707 → exponent 0.5 (ideal).
    const t = integrationTrend([run(HOUR, 1.0), run(2 * HOUR, 0.707)]);
    expect(t).not.toBeNull();
    expect(t?.level).toBe("improving");
    expect(t?.exponent).toBeCloseTo(0.5, 2);
    expect(t?.hoursNow).toBeCloseTo(2.0, 3);
    expect(t?.percentCutIfDoubled).toBe(29);
  });

  it("calls a flat / rising noise trend 'plateaued'", () => {
    // Time trebles but σ doesn't move → exponent ~0 → sky-limited.
    const flat = integrationTrend([run(HOUR, 0.5), run(3 * HOUR, 0.5)]);
    expect(flat?.level).toBe("plateaued");
    expect(flat?.percentCutIfDoubled).toBe(0);
    // Noise actually rose with more time → still plateaued, never a negative promise.
    const rose = integrationTrend([run(HOUR, 0.5), run(3 * HOUR, 0.6)]);
    expect(rose?.level).toBe("plateaued");
    expect(rose?.percentCutIfDoubled).toBe(0);
  });

  it("calls a below-ideal-but-real falloff 'slowing'", () => {
    // ratio 4, σ 1.0 → 0.707 ⇒ exponent 0.25 (between plateau 0.15 and ideal 0.4).
    const t = integrationTrend([run(HOUR, 1.0), run(4 * HOUR, 0.707)]);
    expect(t?.level).toBe("slowing");
    expect(t?.exponent).toBeCloseTo(0.25, 2);
    expect(t?.percentCutIfDoubled).toBe(16);
  });

  it("reads the trend by integration time, not run order, and ignores unmeasured runs", () => {
    // Deepest stack is in the middle; a null-σ run and a null-time run are noise.
    const t = integrationTrend([
      run(2 * HOUR, 0.707),
      run(4 * HOUR, 0.5), // deepest measured (ideal √t vs the shallowest below)
      run(null, 0.4),
      run(HOUR, 1.0), // shallowest measured
    ]);
    expect(t).not.toBeNull();
    // shallow (1h, σ1.0) vs deep (4h, σ0.5): exponent ln(2)/ln(4) = 0.5 → improving.
    expect(t?.level).toBe("improving");
    expect(t?.exponent).toBeCloseTo(0.5, 2);
    expect(t?.hoursNow).toBeCloseTo(4.0, 3);
  });
});
