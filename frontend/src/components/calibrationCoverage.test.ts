import { describe, expect, it } from "vitest";
import {
  masterCoverageLine, masterMissesTooltip, uncoveredTargetsNote,
} from "./calibrationCoverage";

describe("masterCoverageLine", () => {
  it("names how many targets a master reaches", () => {
    expect(masterCoverageLine({ n_covered: 4 }, 6)).toBe("Covers 4 of your 6 targets");
  });
  it("says 'all' rather than N of N, so a fully-covering master reads as done", () => {
    expect(masterCoverageLine({ n_covered: 6 }, 6)).toBe("Covers all 6 of your targets");
  });
  it("is explicit — not silent — when a master matches nothing", () => {
    expect(masterCoverageLine({ n_covered: 0 }, 6))
      .toBe("Doesn't match any of your 6 targets yet");
  });
  it("keeps the singular readable", () => {
    expect(masterCoverageLine({ n_covered: 1 }, 1)).toBe("Covers all 1 of your target");
    expect(masterCoverageLine({ n_covered: 0 }, 1))
      .toBe("Doesn't match any of your 1 target yet");
  });
  it("says nothing at all on a library with no targets yet", () => {
    expect(masterCoverageLine({ n_covered: 0 }, 0)).toBeNull();
  });
});

describe("masterMissesTooltip", () => {
  it("names the targets a master can't be applied to", () => {
    expect(masterMissesTooltip({ missed: ["M 13", "M 51"] }, 6))
      .toBe("Can't be applied to: M 13, M 51");
  });
  it("stays quiet when the master covers everything", () => {
    expect(masterMissesTooltip({ missed: [] }, 6)).toBeNull();
  });
});

describe("uncoveredTargetsNote", () => {
  it("nudges the user about targets no master reaches", () => {
    const note = uncoveredTargetsNote({ uncovered: ["M 13", "M 51"], n_targets: 6 });
    expect(note).toMatch(/2 of your 6 targets have no matching master/);
    expect(note).toMatch(/M 13, M 51/);
    // Plain language, and it says what to do about it.
    expect(note).toMatch(/same exposure, gain and camera/);
  });
  it("reads naturally for a single uncovered target", () => {
    const note = uncoveredTargetsNote({ uncovered: ["M 13"], n_targets: 6 });
    expect(note).toMatch(/^M 13 has no matching master yet/);
  });
  it("only promises hands-off use when auto-calibration is actually on", () => {
    // Off (the default): a matching master still has to be picked, so say so
    // rather than promising something the app won't do.
    const off = uncoveredTargetsNote({ uncovered: ["M 13"], n_targets: 6 });
    expect(off).toMatch(/pick it on the Stack form/);
    expect(off).not.toMatch(/will apply it for you/);
    const on = uncoveredTargetsNote({
      uncovered: ["M 13"], n_targets: 6, auto_apply: true,
    });
    expect(on).toMatch(/AstroStack will apply it for you/);
    expect(on).not.toMatch(/Stack form/);
  });
  it("stays silent when every target is covered", () => {
    expect(uncoveredTargetsNote({ uncovered: [], n_targets: 6 })).toBeNull();
  });
  it("stays silent on a library with no targets", () => {
    expect(uncoveredTargetsNote({ uncovered: [], n_targets: 0 })).toBeNull();
  });
});
