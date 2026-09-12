import { describe, expect, it } from "vitest";
import { siteUnknownCopy } from "./siteUnknown";

describe("siteUnknownCopy", () => {
  it("stops promising more subs will help when the subs carry no location", () => {
    // The bug, stated as a test: on a library of *solved* frames with no
    // SITELAT — the bundled sample — the old sentence told the user to go and
    // solve some subs. Nothing in this copy may say that.
    const copy = siteUnknownCopy("no-site-header");
    expect(copy.body).not.toMatch(/solved some subs/i);
    expect(copy.body).not.toMatch(/it'll just work/i);
    expect(copy.body).toMatch(/won't help/i);
    // …and it still points at the thing that does fix it.
    expect(copy.settingsLead).not.toBe("");
  });

  it("keeps the old sentence where it was right — an empty library", () => {
    const copy = siteUnknownCopy("no-frames");
    expect(copy.title).toBe("Set your observing location");
    expect(copy.body).toMatch(/once you've solved some subs it'll just work/);
    expect(copy.settingsLead).not.toBe("");
  });

  it("does not offer Settings as the fix when the frames can't be read", () => {
    // Typing coordinates would light the planner up over a library that is
    // still unreachable, which is the more important problem.
    const copy = siteUnknownCopy("unreadable");
    expect(copy.body).toMatch(/couldn't open any of them/i);
    expect(copy.settingsLead).toBe("");
  });

  it("falls back to today's sentence for an older backend or an unknown reason", () => {
    // `location_reason` is additive: a backend that doesn't send it must leave
    // the page exactly as it was, never blank and never a new claim.
    for (const reason of [undefined, null, "", "something-new"]) {
      expect(siteUnknownCopy(reason)).toEqual(siteUnknownCopy("no-frames"));
    }
  });

  it("gives every reason a title, a body and a decision about Settings", () => {
    for (const reason of ["no-frames", "no-site-header", "unreadable"] as const) {
      const copy = siteUnknownCopy(reason);
      expect(copy.title.length).toBeGreaterThan(0);
      expect(copy.body.length).toBeGreaterThan(0);
      expect(typeof copy.settingsLead).toBe("string");
    }
  });
});
