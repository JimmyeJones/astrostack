import { describe, expect, it } from "vitest";
import type { SuggestedTarget } from "../api/client";
import {
  describeSuggestion, suggestionHeading, suggestionLabel, suggestionMoonPhrase,
  upForPhrase,
} from "./suggestTargets";

function target(over: Partial<SuggestedTarget> = {}): SuggestedTarget {
  return {
    id: "M27",
    name: "Dumbbell Nebula",
    ra_deg: 299.9,
    dec_deg: 22.7,
    type: "planetary nebula",
    con: "Vul",
    blurb: "A bright planetary nebula in Vulpecula.",
    max_altitude_deg: 64.3,
    transit_utc: "2026-07-22T23:00:00+00:00",
    minutes_above_min_alt: 420,
    moon_separation_deg: 80,
    moon_up_fraction: 0.0,
    usable_start_utc: "2026-07-22T22:00:00+00:00",
    usable_end_utc: "2026-07-23T05:00:00+00:00",
    score: 88,
    size_arcmin: 8,
    framing: { level: "fits", text: "fits comfortably in one frame" },
    ...over,
  };
}

describe("suggestTargets helpers", () => {
  it("labels with the common name, falling back to the id when unnamed", () => {
    expect(suggestionLabel(target())).toBe("Dumbbell Nebula");
    expect(suggestionLabel(target({ name: "" }))).toBe("M27");
    expect(suggestionLabel(target({ name: "   " }))).toBe("M27");
  });

  it("headings pair id with name, or show the id alone when they'd duplicate", () => {
    expect(suggestionHeading(target())).toBe("M27 · Dumbbell Nebula");
    expect(suggestionHeading(target({ name: "" }))).toBe("M27");
    expect(suggestionHeading(target({ id: "M106", name: "M106" }))).toBe("M106");
  });

  it("phrases how long a target is up in friendly units", () => {
    expect(upForPhrase(420)).toBe("up about 7 h tonight");
    expect(upForPhrase(45)).toBe("up about 50 min tonight");
    expect(upForPhrase(150)).toBe("up about 2.5 h tonight");
    // Never below a floor of 10 minutes.
    expect(upForPhrase(3)).toBe("up about 10 min tonight");
  });

  it("speaks to the Moon only when we can say something useful", () => {
    expect(suggestionMoonPhrase(target({ moon_up_fraction: 0.0 }))).toBe("Moon out of the way");
    expect(suggestionMoonPhrase(target({ moon_up_fraction: 0.9, moon_separation_deg: 85 })))
      .toBe("well clear of the Moon");
    // Moon up and close by → no reassuring phrase.
    expect(suggestionMoonPhrase(target({ moon_up_fraction: 0.9, moon_separation_deg: 20 })))
      .toBe("");
  });

  it("describes a suggestion in one plain-language line", () => {
    expect(describeSuggestion(target())).toBe(
      "Climbs to 64°, up about 7 h tonight. Moon out of the way.",
    );
    // No moon clause when there's nothing worth saying.
    expect(describeSuggestion(target({ moon_up_fraction: 0.9, moon_separation_deg: 20 })))
      .toBe("Climbs to 64°, up about 7 h tonight.");
  });
});
