import { describe, expect, it } from "vitest";
import {
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
});

describe("deepeningClip", () => {
  it("builds a slugged filename with the right extension", () => {
    expect(deepeningClip("NGC 7000", "webp").filename).toBe("ngc-7000-deepening.webp");
    expect(deepeningClip("NGC 7000", "png").filename).toBe("ngc-7000-deepening.png");
    expect(deepeningClip("", null).filename).toBe("my-astrophoto-deepening.webp");
  });
});
