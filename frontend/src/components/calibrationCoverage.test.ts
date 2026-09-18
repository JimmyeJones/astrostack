import { describe, expect, it } from "vitest";
import {
  masterCoverageLine, masterMissesTooltip, masterPartialTooltip,
  uncoveredDarkSpecHint, uncoveredTargetsNote,
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
  it("says why each target misses, one per line, when the backend explains", () => {
    const tip = masterMissesTooltip({
      missed: ["M 13", "M 51"],
      missed_detail: [
        { name: "M 13", reason: "your subs are 10s, this dark is 30s" },
        { name: "M 51", reason: "a different camera or binning" },
      ],
    }, 6);
    expect(tip).toBe(
      "Can't be applied to:\nM 13 — your subs are 10s, this dark is 30s\n"
      + "M 51 — a different camera or binning");
  });
  it("falls back to the bare name list on an older backend", () => {
    expect(masterMissesTooltip({ missed: ["M 13"], missed_detail: [] }, 6))
      .toBe("Can't be applied to: M 13");
  });
  it("ignores a malformed detail entry rather than printing 'undefined'", () => {
    const tip = masterMissesTooltip({
      missed: ["M 13", "M 51"],
      missed_detail: [
        { name: "M 13", reason: "" },
        { name: "M 51", reason: "a different camera or binning" },
      ],
    }, 6);
    expect(tip).toBe("Can't be applied to:\nM 51 — a different camera or binning");
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
  it("names the exposure/gain to shoot the darks at when the subs agree", () => {
    const note = uncoveredTargetsNote({
      uncovered: ["M 13", "M 51"], n_targets: 6,
      uncovered_detail: [
        { name: "M 13", exposure_s: 10, gain: 80 },
        { name: "M 51", exposure_s: 10, gain: 80 },
      ],
    });
    expect(note).toMatch(/Shoot them at 10s at gain 80/);
  });
  it("is honest that differently-shot subs need a dark each", () => {
    const note = uncoveredTargetsNote({
      uncovered: ["M 13", "M 51"], n_targets: 6,
      uncovered_detail: [
        { name: "M 13", exposure_s: 10, gain: 80 },
        { name: "M 51", exposure_s: 30, gain: 200 },
      ],
    });
    expect(note).toMatch(/weren't all shot the same way/);
    expect(note).toMatch(/10s at gain 80; 30s at gain 200/);
  });
  it("stays generic rather than inventing numbers the subs never recorded", () => {
    const note = uncoveredTargetsNote({
      uncovered: ["M 13"], n_targets: 6,
      uncovered_detail: [{ name: "M 13", exposure_s: null, gain: null }],
    });
    expect(note).not.toMatch(/Shoot them at/);
    expect(note).toMatch(/same exposure, gain and camera/);
  });
  it("names the exposure alone when the gain wasn't recorded", () => {
    const note = uncoveredTargetsNote({
      uncovered: ["M 13"], n_targets: 6,
      uncovered_detail: [{ name: "M 13", exposure_s: 10, gain: null }],
    });
    expect(note).toMatch(/Shoot them at 10s —/);
  });
  it("stays silent when every target is covered", () => {
    expect(uncoveredTargetsNote({ uncovered: [], n_targets: 6 })).toBeNull();
  });
  it("stays silent on a library with no targets", () => {
    expect(uncoveredTargetsNote({ uncovered: [], n_targets: 0 })).toBeNull();
  });
});


// A target is one *folder*, never one exposure. Shoot it at 10 s one night and
// 30 s the next and the binder reduces it to a median of 20 s — so a 20 s dark
// binds to a target not one of whose frames it matches, and the page that exists
// to answer "do my masters cover my targets?" said "covers" and stopped.

describe("masterCoverageLine — partly covered targets", () => {
  it("says how many targets it only partly reaches", () => {
    expect(masterCoverageLine({ n_covered: 4, n_partial: 1 }, 6))
      .toBe("Covers 4 of your 6 targets — one only partly");
    expect(masterCoverageLine({ n_covered: 6, n_partial: 2 }, 6))
      .toBe("Covers all 6 of your targets — 2 only partly");
  });
  it("is byte-identical on an ordinary library, and against an older backend", () => {
    expect(masterCoverageLine({ n_covered: 4, n_partial: 0 }, 6))
      .toBe("Covers 4 of your 6 targets");
    expect(masterCoverageLine({ n_covered: 4 }, 6))
      .toBe("Covers 4 of your 6 targets");
  });
  it("never contradicts 'matches nothing' — a master that covers none can't partly cover", () => {
    expect(masterCoverageLine({ n_covered: 0, n_partial: 0 }, 6))
      .toBe("Doesn't match any of your 6 targets yet");
  });
});

describe("masterPartialTooltip", () => {
  it("names the subs a bound dark misses", () => {
    expect(masterPartialTooltip({
      partial_detail: [
        { name: "M 42", reason: "M 42 was shot at 10s and 30s, and this dark is 10s — it matches the 10s subs but not the 30s ones." },
      ],
    })).toBe("Only part of:\nM 42 was shot at 10s and 30s, and this dark is 10s — it matches the 10s subs but not the 30s ones.");
  });
  it("stays quiet on the ordinary single-exposure library", () => {
    expect(masterPartialTooltip({ partial_detail: [] })).toBeNull();
    expect(masterPartialTooltip({})).toBeNull();
  });
  it("ignores a malformed entry rather than printing an empty line", () => {
    expect(masterPartialTooltip({
      partial_detail: [{ name: "", reason: "" }],
    })).toBeNull();
  });
});

describe("uncoveredDarkSpecHint — the lengths to actually go and shoot", () => {
  it("names both of a mixed target's lengths, never the median between them", () => {
    const hint = uncoveredDarkSpecHint([
      { name: "M 42", exposure_s: 20, gain: 80, exposures_s: [10, 30] },
    ]);
    expect(hint).not.toContain("20s");
    expect(hint).toContain("10s at gain 80");
    expect(hint).toContain("30s at gain 80");
    expect(hint).toContain("need a dark each");
  });
  it("is unchanged on a single-exposure target", () => {
    expect(uncoveredDarkSpecHint([
      { name: "M 42", exposure_s: 10, gain: 80, exposures_s: [10] },
    ])).toBe(" Shoot them at 10s at gain 80 — that's what those subs were shot at.");
  });
  it("falls back to the median against an older backend that sends no set", () => {
    expect(uncoveredDarkSpecHint([
      { name: "M 42", exposure_s: 10, gain: 80 },
    ])).toBe(" Shoot them at 10s at gain 80 — that's what those subs were shot at.");
  });
  it("still says nothing when nothing was recorded", () => {
    expect(uncoveredDarkSpecHint([
      { name: "M 42", exposure_s: null, gain: null, exposures_s: [] },
    ])).toBe("");
  });
});
