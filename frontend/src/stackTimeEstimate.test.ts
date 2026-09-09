import { describe, expect, it } from "vitest";
import { FAR_EXTRAPOLATION, stackTimeLine } from "./stackTimeEstimate";

describe("stackTimeLine", () => {
  it("says how long, and what it is standing on", () => {
    const line = stackTimeLine(
      { seconds: 2 * 3600 + 50 * 60, basis_runs: 3, basis_frames: 1200 }, 1400);
    expect(line).toBe(
      "About 2 h 50 min to run — from your last 3 stacks of this target.");
  });

  it("names a single past run in the singular", () => {
    const line = stackTimeLine(
      { seconds: 600, basis_runs: 1, basis_frames: 40 }, 40);
    expect(line).toBe("About 10 min to run — from your last stack of this target.");
  });

  it("softens to 'roughly' when the run dwarfs the runs it learned from", () => {
    const est = { seconds: 3600, basis_runs: 2, basis_frames: 100 };
    // A rate measured on 100 subs, projected onto 4,000, is an extrapolation.
    expect(stackTimeLine(est, 100 * FAR_EXTRAPOLATION)).toMatch(/^Roughly /);
    // …and a stack merely twice the size is not.
    expect(stackTimeLine(est, 200)).toMatch(/^About /);
  });

  it("says nothing at all when there is no estimate", () => {
    // No comparable history, and an older backend that sends no field: the
    // form shows no line rather than a hedged one.
    expect(stackTimeLine(null, 100)).toBeNull();
    expect(stackTimeLine(undefined, 100)).toBeNull();
  });

  it("refuses a nonsense duration rather than printing it", () => {
    expect(stackTimeLine({ seconds: 0, basis_runs: 1, basis_frames: 40 }, 40))
      .toBeNull();
    expect(stackTimeLine({ seconds: -5, basis_runs: 1, basis_frames: 40 }, 40))
      .toBeNull();
    expect(stackTimeLine(
      { seconds: Number.NaN, basis_runs: 1, basis_frames: 40 }, 40)).toBeNull();
    expect(stackTimeLine({ seconds: 600, basis_runs: 0, basis_frames: 40 }, 40))
      .toBeNull();
  });

  it("speaks the same way as the running job's ETA", () => {
    // Both go through `formatEtaSeconds`, so a stack estimated at "40 min"
    // before the button counts down in the same unit once it is running.
    expect(stackTimeLine({ seconds: 40 * 60, basis_runs: 1, basis_frames: 40 }, 40))
      .toContain("40 min");
  });
});
