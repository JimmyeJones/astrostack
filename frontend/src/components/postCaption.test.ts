import { describe, it, expect } from "vitest";
import { postCaption } from "./postCaption";

describe("postCaption", () => {
  it("builds the full sentence from every fact", () => {
    expect(
      postCaption({
        name: "Orion Nebula",
        catalogId: "M42",
        type: "nebula",
        nFrames: 240,
        integrationS: 40 * 60,
        captureNightStart: "2026-07-20",
        captureNightEnd: "2026-07-20",
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
      captureNightStart: "2026-09-01",
      captureNightEnd: "2026-09-01",
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

  // The date was the one fact this caption used to get *wrong*: it was fed
  // `run.timestamp_utc`, when the stack ran, and published it as when the
  // picture was shot. These pin that it now says the capture window or nothing.
  it("names the night the subs were shot, not the day the stack ran", () => {
    const c = postCaption({
      name: "Orion Nebula", catalogId: "M42", type: "nebula", nFrames: 240,
      captureNightStart: "2024-11-15", captureNightEnd: "2024-11-15",
    });
    expect(c).toContain("shot on 15 Nov 2024 with a Seestar");
    expect(c).not.toContain("2026");
  });

  it("says 'between' for a picture built over several nights", () => {
    const c = postCaption({
      name: "Andromeda Galaxy", catalogId: "M31", nFrames: 600,
      captureNightStart: "2024-11-15", captureNightEnd: "2024-11-18",
    });
    expect(c).toContain("shot between 15 and 18 Nov 2024 with a Seestar");
  });

  it("says how many nights a picture took when the run recorded it", () => {
    // The sentence a person actually says out loud about their picture. A span
    // alone cannot supply it: 15→18 Nov is equally consistent with two nights.
    const c = postCaption({
      name: "Andromeda Galaxy", catalogId: "M31", nFrames: 600,
      captureNightStart: "2024-11-15", captureNightEnd: "2024-11-18",
      captureNights: 4,
    });
    expect(c).toContain(
      "shot over 4 nights, between 15 and 18 Nov 2024 with a Seestar");
  });

  it("drops the date clause entirely when no capture window was recorded", () => {
    // Every run made before the app recorded one — i.e. the owner's whole
    // library on the day of the upgrade. Saying nothing is the honest outcome;
    // reaching for the stack stamp is the bug.
    const c = postCaption({ name: "Ring Nebula", catalogId: "M57", nFrames: 40 });
    expect(c).toBe("Ring Nebula (M57) — a stack of 40 subs, shot with a Seestar.");
    expect(c).not.toContain("shot on");
  });

  it("still names the one night it has when only one end was recorded", () => {
    expect(postCaption({ name: "M13", nFrames: 10, captureNightStart: "2024-06-02" }))
      .toContain("shot on 2 Jun 2024");
    expect(postCaption({ name: "M13", nFrames: 10, captureNightEnd: "2024-06-02" }))
      .toContain("shot on 2 Jun 2024");
  });

  it("ignores an unparseable window rather than printing a placeholder", () => {
    const c = postCaption({
      name: "M13", nFrames: 10,
      captureNightStart: "not-a-date", captureNightEnd: "2024-13-40",
    });
    expect(c).toContain("shot with a Seestar");
    expect(c).not.toContain("—date");
  });

  it("tells the object's story, between the picture and its scale", () => {
    expect(
      postCaption({
        name: "Andromeda Galaxy",
        catalogId: "M31",
        type: "galaxy",
        blurb: "The nearest large spiral galaxy to our own, about 2.5 million "
          + "light-years away.",
        nFrames: 512,
        integrationS: 85 * 60,
        captureNightStart: "2026-11-03",
        captureNightEnd: "2026-11-06",
        captureNights: 3,
        scaleBar: { moon_comparison: "the whole frame is about 2.4 full Moons wide" },
      }),
    ).toBe(
      "Andromeda Galaxy (M31) — a stack of 512 subs (1.4 h total), "
        + "shot over 3 nights, between 3 and 6 Nov 2026 with a Seestar. "
        + "The nearest large spiral galaxy to our own, about 2.5 million "
        + "light-years away. "
        + "The whole frame is about 2.4 full Moons wide.",
    );
  });

  it("drops the bare type word when there is a story, and keeps it when there isn't", () => {
    // The blurb says the type in better words; both together stutter.
    const told = postCaption({
      name: "North America Nebula", catalogId: "NGC 7000", type: "nebula",
      blurb: "A vast emission nebula in Cygnus shaped like the continent of "
        + "North America.",
      nFrames: 50,
    });
    expect(told).toContain("North America Nebula (NGC 7000) — a stack of 50 subs");
    expect(told).not.toContain(", a nebula —");
    // …and an uncurated object is exactly what it was before this existed.
    expect(postCaption({
      name: "North America Nebula", catalogId: "NGC 7000", type: "nebula", nFrames: 50,
    })).toBe("North America Nebula (NGC 7000), a nebula — a stack of 50 subs, "
      + "shot with a Seestar.");
  });

  it("says nothing extra for a blank blurb or an older backend that omits it", () => {
    const bare = "Ring Nebula (M57), a planetary nebula — a stack of 40 subs, "
      + "shot with a Seestar.";
    expect(postCaption({
      name: "Ring Nebula", catalogId: "M57", type: "planetary nebula", nFrames: 40,
      blurb: "   ",
    })).toBe(bare);
    expect(postCaption({
      name: "Ring Nebula", catalogId: "M57", type: "planetary nebula", nFrames: 40,
      blurb: null,
    })).toBe(bare);
  });

  it("never tells a story about a target it could not identify", () => {
    // A blurb only reaches a caller from a catalogue match, so one arriving
    // beside no identity describes something we never named — say nothing.
    const c = postCaption({
      fallbackName: "My backyard field", nFrames: 12,
      blurb: "A vast emission nebula in Cygnus.",
    });
    expect(c).toBe("My backyard field — a stack of 12 subs, shot with a Seestar.");
  });

  it("finishes a story that forgot its full stop, so it can't run into the scale", () => {
    const c = postCaption({
      name: "M13", nFrames: 10,
      blurb: "A tight ball of several hundred thousand ancient stars",
      scaleBar: { moon_comparison: "the whole frame is about 5.4 full Moons wide" },
    });
    expect(c).toContain("ancient stars. The whole frame");
  });
});
