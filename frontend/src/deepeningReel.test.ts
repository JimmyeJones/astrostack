import { describe, expect, it } from "vitest";
import {
  cumulativeNights,
  deepeningBlurb,
  deepeningCaption,
  deepeningClip,
  shortDate,
} from "./deepeningReel";

describe("shortDate", () => {
  it("formats a timestamp as a short day/month", () => {
    expect(shortDate("2026-07-28T00:00:00Z")).toMatch(/28/);
  });
  it("returns null for missing or unparseable input", () => {
    expect(shortDate(null)).toBeNull();
    expect(shortDate(undefined)).toBeNull();
    expect(shortDate("not-a-date")).toBeNull();
  });
});

describe("deepeningCaption", () => {
  it("joins name, stack count, sub range, and date range", () => {
    const cap = deepeningCaption("M31", {
      available: true, n_stacks: 3,
      first_subs: 120, last_subs: 1240,
      first_utc: "2026-06-28T00:00:00Z", last_utc: "2026-07-28T00:00:00Z",
    });
    expect(cap).toContain("M31");
    expect(cap).toContain("3 stacks");
    expect(cap).toContain("120 → 1,240 subs");
    expect(cap.split(" · ").length).toBe(4);
  });

  it("drops the name clause when unnamed and never prints a blank sub range", () => {
    const cap = deepeningCaption("", {
      available: true, n_stacks: 2, last_subs: 505,
      first_utc: null, last_utc: null,
    });
    expect(cap.startsWith("2 stacks")).toBe(true);
    expect(cap).toContain("505 subs");
    expect(cap).not.toContain("→");        // no first_subs → no range arrow
  });

  it("collapses an equal sub count / single date to one value", () => {
    const cap = deepeningCaption("NGC 7000", {
      available: true, n_stacks: 2,
      first_subs: 200, last_subs: 200,
      first_utc: "2026-07-10T00:00:00Z", last_utc: "2026-07-10T00:00:00Z",
    });
    expect(cap).toContain("200 subs");
    expect(cap).not.toContain("→");
  });

  // On a card titled "night after night", a bare date range reads as when the
  // subs were shot. It only *is* that when the backend says so — the two differ
  // by years on a re-stacked back catalogue — so the caption names its clock.
  it("says the dates are when the subs were shot when the series is capture-dated", () => {
    const cap = deepeningCaption("M31", {
      available: true, n_stacks: 3, first_subs: 120, last_subs: 1240,
      first_utc: "2026-06-28T00:00:00Z", last_utc: "2026-07-28T00:00:00Z",
      dated_by: "capture",
    });
    expect(cap).toContain(`shot ${shortDate("2026-06-28T00:00:00Z")} → `
      + `${shortDate("2026-07-28T00:00:00Z")}`);
    expect(cap).not.toContain("stacked");
  });

  it("says the dates are stack dates when that is all the app knows", () => {
    const cap = deepeningCaption("M31", {
      available: true, n_stacks: 3, first_subs: 120, last_subs: 1240,
      first_utc: "2026-06-28T00:00:00Z", last_utc: "2026-07-28T00:00:00Z",
      dated_by: "stack",
    });
    expect(cap).toContain(`stacked ${shortDate("2026-06-28T00:00:00Z")} → `
      + `${shortDate("2026-07-28T00:00:00Z")}`);
  });

  it("qualifies a single date too, and leaves an older backend's range bare", () => {
    expect(deepeningCaption("M31", {
      available: true, n_stacks: 2, last_subs: 200,
      first_utc: "2026-07-10T00:00:00Z", last_utc: "2026-07-10T00:00:00Z",
      dated_by: "capture",
    })).toContain(`shot ${shortDate("2026-07-10T00:00:00Z")}`);
    // No `dated_by` (an older backend) ⇒ exactly the caption it always produced.
    expect(deepeningCaption("M31", {
      available: true, n_stacks: 2, last_subs: 200,
      first_utc: "2026-07-10T00:00:00Z", last_utc: "2026-07-10T00:00:00Z",
    })).toBe(`M31 · 2 stacks · 200 subs · ${shortDate("2026-07-10T00:00:00Z")}`);
  });
});

describe("deepeningBlurb", () => {
  it("states the depth gain in plain language with a rough factor", () => {
    const b = deepeningBlurb("M31", {
      available: true, n_stacks: 3, first_subs: 120, last_subs: 1240,
    });
    expect(b).toContain("120");
    expect(b).toContain("1,240");
    expect(b).toMatch(/10×|10.0×/);        // 1240/120 ≈ 10.3×
  });

  it("falls back to a generic line without sub counts", () => {
    const b = deepeningBlurb("M31", { available: true, n_stacks: 2 });
    expect(b).toContain("2 stacks");
    expect(b).toContain("M31");
  });

  // The reel is ordered by when the subs were shot, not by depth, so a night
  // stacked on its own after a deeper run lands *last* with fewer subs in it
  // (100 → 200 → 30 is a real shape off `deepening_series`). Promising "cleaner
  // and deeper … more subs each time" over that reel is an untruth the caption
  // underneath already contradicts.
  it("stops promising a steady deepening when a step holds fewer subs", () => {
    const b = deepeningBlurb("M31", {
      available: true, n_stacks: 3, first_subs: 100, last_subs: 30,
      depth_monotone: false,
    });
    expect(b).not.toContain("cleaner and deeper");
    expect(b).not.toContain("more subs each time");
    expect(b).toContain("grainier");
    expect(b).toContain("M31");
    // The figures are still there — the reader can see which way it went.
    expect(b).toContain("100");
    expect(b).toContain("30");
  });

  it("still says it plainly when the counts are missing", () => {
    const b = deepeningBlurb("M31", {
      available: true, n_stacks: 3, depth_monotone: false,
    });
    expect(b).toContain("grainier");
    expect(b).not.toContain("undefined");
    expect(b).not.toContain("()");
  });

  it("keeps today's wording when the depth really does only grow", () => {
    const grows = deepeningBlurb("M31", {
      available: true, n_stacks: 3, first_subs: 120, last_subs: 1240,
      depth_monotone: true,
    });
    expect(grows).toContain("cleaner and deeper");
    // …and on an older backend, which sends no verdict at all.
    const older = deepeningBlurb("M31", {
      available: true, n_stacks: 3, first_subs: 120, last_subs: 1240,
    });
    expect(older).toBe(grows);
  });
});

describe("deepeningClip", () => {
  it("builds a slugged filename with the right extension", () => {
    expect(deepeningClip("NGC 7000", "webp").filename).toBe("ngc-7000-deepening.webp");
    expect(deepeningClip("NGC 7000", "png").filename).toBe("ngc-7000-deepening.png");
    expect(deepeningClip("", null).filename).toBe("my-astrophoto-deepening.webp");
  });
});


describe("the reel found in stacks you already have", () => {
  const cumulative = {
    available: true, n_stacks: 3, first_subs: 120, last_subs: 300,
    first_utc: "2026-05-01T21:00:00Z", last_utc: "2026-05-03T21:00:00Z",
    dated_by: "capture" as const, depth_monotone: true,
    night_steps: [1, 2, 3],
  };

  it("reads the last step as how many nights the reel ends on", () => {
    expect(cumulativeNights(cumulative)).toBe(3);
  });

  it("says nothing on an older backend, or on a series with nothing to describe", () => {
    // No field at all — the wire shape before this existed.
    expect(cumulativeNights({ available: true, n_stacks: 3 })).toBeNull();
    expect(cumulativeNights({ ...cumulative, night_steps: null })).toBeNull();
    // One step is not a progression, and neither is a reel that ends on night 1.
    expect(cumulativeNights({ ...cumulative, night_steps: [1] })).toBeNull();
    expect(cumulativeNights({ ...cumulative, night_steps: [1, 1] })).toBeNull();
    // ...and a value that is not a list of numbers is not trusted into the copy.
    expect(cumulativeNights({
      ...cumulative,
      night_steps: ["1", "3"] as unknown as number[],
    })).toBeNull();
  });

  it("tells the beginner what the reel is, in nights rather than in stacks", () => {
    const b = deepeningBlurb("M31", cumulative);
    expect(b).toContain("night by night");
    expect(b).toContain("all 3 nights");
    // The point of this half: it is built from stacks that already exist.
    expect(b).toContain("already have");
    expect(b).not.toContain("undefined");
  });

  it("names the nights in the caption without losing what was already there", () => {
    const c = deepeningCaption("M31", cumulative);
    expect(c).toContain("3 nights, cumulative");
    // Nothing removed: the target, the step count, the depth and the clock all
    // still read as they did.
    expect(c).toContain("M31");
    expect(c).toContain("3 stacks");
    expect(c).toContain("120 → 300 subs");
    expect(c).toContain("shot ");
  });

  it("leaves a series that is not cumulative exactly as it was", () => {
    const plain = { ...cumulative, night_steps: null };
    expect(deepeningCaption("M31", plain)).toBe(
      deepeningCaption("M31", { available: true, n_stacks: 3, first_subs: 120,
        last_subs: 300, first_utc: "2026-05-01T21:00:00Z",
        last_utc: "2026-05-03T21:00:00Z", dated_by: "capture" }));
    expect(deepeningBlurb("M31", plain)).toContain("cleaner and deeper");
  });

  it("stands aside for the reel that steps back in depth", () => {
    // `depth_monotone: false` is the stronger warning — a step that gets
    // grainier — and it must not be replaced by the cheerful night-by-night
    // sentence just because the nights happen to nest.
    const b = deepeningBlurb("M31", { ...cumulative, depth_monotone: false });
    expect(b).toContain("grainier");
    expect(b).not.toContain("night by night");
  });
});
