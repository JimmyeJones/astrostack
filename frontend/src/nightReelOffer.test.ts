import { describe, expect, it } from "vitest";
import {
  nightReelOfferBlurb,
  nightReelOfferCost,
  nightReelStackHref,
  type NightReelOffer,
} from "./nightReelOffer";

const OFFER: NightReelOffer = {
  run_id: 12, nights: 6, subs: 1234, last_duration_s: 1500,
};

describe("nightReelOfferBlurb", () => {
  it("names the target and every night the clip would cover", () => {
    const b = nightReelOfferBlurb("M 31", OFFER);
    expect(b).toContain("M 31");
    expect(b).toContain("night by night");
    expect(b).toContain("all 6");
  });

  it("says why there is no clip yet, and what makes one", () => {
    const b = nightReelOfferBlurb("M 31", OFFER);
    expect(b).toContain("stacked it in one go");
    expect(b).toContain("watch it appear");
  });

  it("falls back to 'your target' with no name", () => {
    expect(nightReelOfferBlurb("  ", OFFER)).toContain("your target");
    expect(nightReelOfferBlurb(undefined, OFFER)).toContain("your target");
  });
});

describe("nightReelOfferCost", () => {
  it("prices the re-stack from the run's own wall clock, not the snapshots", () => {
    const c = nightReelOfferCost(OFFER);
    expect(c).toContain("add no time of their own");
    expect(c).toContain("1,234 subs");
    expect(c).toContain("25 min");
    expect(c).toContain("how long that stack took");
  });

  it("drops the number rather than guessing for an untimed run", () => {
    const c = nightReelOfferCost({ ...OFFER, last_duration_s: null });
    expect(c).toContain("as long as that stack took");
    expect(c).not.toMatch(/\d+ min/);
  });

  it("still says it adds a stack — the wall's picture changes", () => {
    // The one surprise somebody pressing this could not otherwise predict.
    for (const secs of [1500, null]) {
      const c = nightReelOfferCost({ ...OFFER, last_duration_s: secs });
      expect(c).toContain("stays in History");
      expect(c).toContain("becomes this target's picture");
    }
  });

  it("stays readable when the sub count is unknown", () => {
    const c = nightReelOfferCost({ ...OFFER, subs: 0 });
    expect(c).toContain("stacking your subs again");
  });
});

describe("nightReelStackHref", () => {
  it("pre-fills the form from the run, opens Advanced and ticks the switch", () => {
    expect(nightReelStackHref("M_31", OFFER)).toBe(
      "/targets/M_31/stack?from=12&open=advanced&reel=1");
  });

  it("escapes a safe name that needs it", () => {
    expect(nightReelStackHref("NGC 7000", OFFER)).toContain("/targets/NGC%207000/stack");
  });
});
