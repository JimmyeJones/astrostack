import { describe, expect, it } from "vitest";
import {
  type EtaSample,
  etaLabel,
  formatEtaSeconds,
  isNewPhase,
  phaseEtaSeconds,
  updateEtaAnchor,
} from "./jobEta";

const s = (phase: string, total: number, done: number, tMs: number): EtaSample =>
  ({ phase, total, done, tMs });

describe("isNewPhase", () => {
  it("is false while a step advances monotonically", () => {
    expect(isNewPhase(s("aligning", 100, 10, 0), s("aligning", 100, 25, 1500))).toBe(false);
  });
  it("is true when the step label changes", () => {
    expect(isNewPhase(s("pass 1", 100, 90, 0), s("pass 2", 100, 5, 1500))).toBe(true);
  });
  it("is true when the same-labelled step restarts (done goes backwards)", () => {
    // A two-pass stack reuses the label but resets done to 0 for pass 2.
    expect(isNewPhase(s("stacking", 100, 100, 0), s("stacking", 100, 0, 1500))).toBe(true);
  });
  it("is true when the step's total changes", () => {
    expect(isNewPhase(s("stacking", 100, 10, 0), s("stacking", 250, 10, 1500))).toBe(true);
  });
});

describe("updateEtaAnchor", () => {
  it("anchors at the first observation", () => {
    const first = s("aligning", 100, 3, 1000);
    expect(updateEtaAnchor(null, first)).toBe(first);
  });
  it("keeps the anchor while the step advances", () => {
    const anchor = s("aligning", 100, 3, 1000);
    const later = s("aligning", 100, 40, 5000);
    expect(updateEtaAnchor(anchor, later)).toBe(anchor);
  });
  it("re-anchors when the step (re)starts", () => {
    const anchor = s("pass 1", 100, 100, 1000);
    const next = s("pass 2", 100, 0, 5000);
    expect(updateEtaAnchor(anchor, next)).toBe(next);
  });
});

describe("phaseEtaSeconds", () => {
  it("projects the remaining time from the observed rate", () => {
    // 20 items in 4 s ⇒ 5 items/s; 80 remaining ⇒ 16 s.
    const anchor = s("aligning", 100, 0, 0);
    const cur = s("aligning", 100, 20, 4000);
    expect(phaseEtaSeconds(anchor, cur)).toBeCloseTo(16, 5);
  });
  it("returns null with no measurable progress yet", () => {
    const anchor = s("aligning", 100, 5, 0);
    expect(phaseEtaSeconds(anchor, s("aligning", 100, 5, 1500))).toBeNull();
  });
  it("returns null when the step has no total or is already complete", () => {
    expect(phaseEtaSeconds(s("saving", 0, 0, 0), s("saving", 0, 0, 1500))).toBeNull();
    expect(phaseEtaSeconds(s("aligning", 100, 0, 0), s("aligning", 100, 100, 4000))).toBeNull();
  });
  it("returns null when no time has elapsed since the anchor", () => {
    expect(phaseEtaSeconds(s("aligning", 100, 0, 1000), s("aligning", 100, 20, 1000))).toBeNull();
  });
});

describe("formatEtaSeconds", () => {
  it("rounds sub-minute estimates to 5 s (min 5 s)", () => {
    expect(formatEtaSeconds(3)).toBe("5 sec");
    expect(formatEtaSeconds(12)).toBe("10 sec");
    expect(formatEtaSeconds(58)).toBe("60 sec");
  });
  it("shows whole minutes", () => {
    expect(formatEtaSeconds(90)).toBe("2 min");
    expect(formatEtaSeconds(600)).toBe("10 min");
  });
  it("shows hours and minutes", () => {
    expect(formatEtaSeconds(3600)).toBe("1 h");
    expect(formatEtaSeconds(3600 + 20 * 60)).toBe("1 h 20 min");
  });
});

describe("etaLabel", () => {
  it("labels a normal estimate", () => {
    // 1 item in 1.5 s over a 100-item step ⇒ 99 remaining ⇒ ~148 s ⇒ ~2 min.
    expect(etaLabel(s("aligning", 100, 1, 0), s("aligning", 100, 2, 1500)))
      .toBe("~2 min left");
  });
  it("says 'almost done' when only a moment remains", () => {
    // 50 in 1 s, 1 remaining ⇒ 0.02 s.
    expect(etaLabel(s("saving", 100, 49, 0), s("saving", 100, 99, 1000)))
      .toBe("almost done");
  });
  it("shows nothing without a usable estimate", () => {
    expect(etaLabel(s("aligning", 100, 5, 0), s("aligning", 100, 5, 1500))).toBeNull();
  });
  it("suppresses an implausibly-long early guess (>24 h)", () => {
    // 1 item in 1 s over a 1e9-item step ⇒ ~1e9 s — a noisy early guess.
    expect(etaLabel(s("aligning", 1_000_000_000, 0, 0), s("aligning", 1_000_000_000, 1, 1000)))
      .toBeNull();
  });
});
