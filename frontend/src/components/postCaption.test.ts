import { describe, it, expect } from "vitest";
import { postCaption, formatCaptionDate } from "./postCaption";

describe("formatCaptionDate", () => {
  it("formats an ISO UTC stamp as a friendly day-month-year", () => {
    expect(formatCaptionDate("2026-07-20T22:14:03")).toBe("20 Jul 2026");
    expect(formatCaptionDate("2026-01-05")).toBe("5 Jan 2026");
  });
  it("reads off the string (no timezone shift) and rejects junk", () => {
    // A UTC midnight stamp must not roll back a day in a western timezone.
    expect(formatCaptionDate("2026-12-31T00:00:00")).toBe("31 Dec 2026");
    expect(formatCaptionDate("")).toBeNull();
    expect(formatCaptionDate(null)).toBeNull();
    expect(formatCaptionDate("not-a-date")).toBeNull();
    expect(formatCaptionDate("2026-13-40")).toBeNull();
  });
});

describe("postCaption", () => {
  it("builds the full sentence from every fact", () => {
    expect(
      postCaption({
        name: "Orion Nebula",
        catalogId: "M42",
        type: "nebula",
        nFrames: 240,
        integrationS: 40 * 60,
        dateLabel: "20 Jul 2026",
        scaleBar: { moon_comparison: "the whole frame is about 5.4 full Moons wide" },
      }),
    ).toBe(
      "Orion Nebula (M42), a nebula — a stack of 240 subs (40 min total), " +
        "shot on 20 Jul 2026 with a Seestar. " +
        "The whole frame is about 5.4 full Moons wide.",
    );
  });

  it("uses the correct article for a vowel-initial type", () => {
    const c = postCaption({ name: "Wild Duck Cluster", catalogId: "M11", type: "open cluster", nFrames: 30 });
    expect(c).toContain("(M11), an open cluster —");
  });

  it("drops the scale clause when there's no WCS", () => {
    const c = postCaption({
      name: "Andromeda Galaxy",
      catalogId: "M31",
      type: "galaxy",
      nFrames: 100,
      integrationS: 3600,
      dateLabel: "1 Sep 2026",
      scaleBar: null,
    });
    expect(c).toBe(
      "Andromeda Galaxy (M31), a galaxy — a stack of 100 subs (1.0 h total), " +
        "shot on 1 Sep 2026 with a Seestar.",
    );
    expect(c).not.toContain("Moon");
  });

  it("degrades to a bare designation with no common name", () => {
    const c = postCaption({ name: "", catalogId: "NGC 7000", type: "nebula", nFrames: 50 });
    expect(c).toBe("NGC 7000, a nebula — a stack of 50 subs, shot with a Seestar.");
  });

  it("falls back to the target name (no type) when unidentified", () => {
    const c = postCaption({ fallbackName: "My backyard field", nFrames: 12, integrationS: 5 * 60 });
    expect(c).toBe("My backyard field — a stack of 12 subs (5 min total), shot with a Seestar.");
    // No identity → never invent a type appositive after the subject.
    expect(c.startsWith("My backyard field — ")).toBe(true);
  });

  it("falls back to a generic subject when nothing at all is known", () => {
    const c = postCaption({ nFrames: 3 });
    expect(c).toBe("My astrophoto — a stack of 3 subs, shot with a Seestar.");
  });

  it("uses singular grammar for a one-frame stack", () => {
    const c = postCaption({ name: "Ring Nebula", catalogId: "M57", type: "planetary nebula", nFrames: 1 });
    expect(c).toContain("a stack of 1 sub,");
    expect(c).not.toContain("1 subs");
    expect(c).toContain("a planetary nebula");
  });

  it("omits the stack clause when the frame count is missing", () => {
    const c = postCaption({ name: "Pleiades", catalogId: "M45", type: "open cluster", nFrames: null });
    expect(c).toBe("Pleiades (M45), an open cluster — shot with a Seestar.");
  });

  it("ignores a zero/negative integration but keeps the sub count", () => {
    const c = postCaption({ name: "Dumbbell Nebula", catalogId: "M27", nFrames: 80, integrationS: 0 });
    expect(c).toContain("a stack of 80 subs,");
    expect(c).not.toContain("total");
  });
});
