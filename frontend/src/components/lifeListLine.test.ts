import { describe, expect, it } from "vitest";
import type { LifeListCounts } from "../api/client";
import { HOME_STRAIGHT_REMAINING, lifeListLine } from "./lifeListLine";

const counts = (messier_captured: number, messier_total = 110): LifeListCounts => ({
  messier_captured, messier_total, other_captured: 0, other_total: 47,
});

describe("lifeListLine", () => {
  it("says nothing before the first famous object is captured", () => {
    // A fresh install already has a first-run card telling it what to do; a
    // 0-of-110 scoreboard for a game that hasn't started is not a nudge.
    expect(lifeListLine(counts(0))).toBe("");
  });

  it("says nothing when the backend hasn't answered (or is older)", () => {
    expect(lifeListLine(undefined)).toBe("");
    expect(lifeListLine(null)).toBe("");
  });

  it("counts plainly on the way up", () => {
    expect(lifeListLine(counts(12))).toBe(
      "You've photographed 12 of the 110 Messier objects.");
  });

  it("names the halfway milestone once it is true", () => {
    expect(lifeListLine(counts(54))).not.toContain("halfway");
    expect(lifeListLine(counts(55))).toContain("over halfway");
  });

  it("switches to what's left on the home straight, because that's the hook", () => {
    const line = lifeListLine(counts(110 - HOME_STRAIGHT_REMAINING));
    expect(line).toContain(`just ${HOME_STRAIGHT_REMAINING} to go`);
    // One reads as a word, not a digit — it is the sentence someone screenshots.
    expect(lifeListLine(counts(109))).toContain("just one to go");
    expect(lifeListLine(counts(109))).not.toContain("halfway");
  });

  it("celebrates the finished list rather than saying '0 to go'", () => {
    expect(lifeListLine(counts(110))).toContain("the whole list");
  });

  it("refuses a nonsense tally instead of printing one", () => {
    // More captured than exist, or a total of zero: both mean the counts are
    // not what this sentence thinks they are, and a wrong number in the one
    // line a beginner reads every session is worse than no line.
    expect(lifeListLine(counts(120))).toBe("");
    expect(lifeListLine(counts(3, 0))).toBe("");
    expect(lifeListLine({ messier_captured: Number.NaN, messier_total: 110,
                          other_captured: 0, other_total: 0 })).toBe("");
  });

  it("does not hard-code 110 — the count comes from the catalog", () => {
    expect(lifeListLine(counts(2, 40))).toBe(
      "You've photographed 2 of the 40 Messier objects.");
  });
});
