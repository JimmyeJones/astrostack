import { describe, expect, it } from "vitest";
import {
  CLOSING_WHY, closingHeadline, closingTargetLine, closingUrgentSentence,
  lastNightLabel, urgentlyClosing, weeksLeftPhrase,
} from "./closingSeason";
import type { ClosingTarget, SeasonClosing } from "./api/client";

function row(over: Partial<ClosingTarget> = {}): ClosingTarget {
  return {
    safe: "m_42", name: "M 42", minutes_now: 180, weeks_left: 3,
    last_night: "2026-03-03", total_exposure_s: 3600, noise_gain: 0.29,
    ...over,
  };
}

function plan(targets: ClosingTarget[]): SeasonClosing {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    generated_utc: "2026-01-20T21:00:00+00:00",
    min_altitude_deg: 30, horizon_weeks: 8, targets,
  };
}

describe("weeksLeftPhrase", () => {
  it("counts in weeks, and says so when there is no next week", () => {
    expect(weeksLeftPhrase(0)).toBe("this is its last week");
    expect(weeksLeftPhrase(1)).toBe("about a week left");
    expect(weeksLeftPhrase(5)).toBe("about 5 weeks left");
  });

  it("never invents a negative or fractional countdown", () => {
    // The scan samples whole weeks, so anything else is a bug upstream — this
    // must degrade to a sentence, never to "about -1 weeks left".
    expect(weeksLeftPhrase(-4)).toBe("this is its last week");
    expect(weeksLeftPhrase(2.4)).toBe("about 2 weeks left");
  });
});

describe("lastNightLabel", () => {
  it("names the evening's own date, and hands back anything it can't parse", () => {
    // Parsed at local noon: a timezone offset must not roll the evening onto
    // the neighbouring day.
    expect(lastNightLabel("2026-03-03")).toContain("3");
    expect(lastNightLabel("not-a-date")).toBe("not-a-date");
  });
});

describe("closingTargetLine", () => {
  it("says how long is left and what you already have on it", () => {
    const line = closingTargetLine(row());
    expect(line).toContain("about 3 weeks left");
    expect(line).toContain("you have 1.0 h on it");
    expect(line).toContain("last good night around");
  });

  it("is honest about a target with nothing kept yet", () => {
    // "you have — on it" would be worse than useless; a target you have not
    // actually kept anything of is the one most worth a clear night.
    expect(closingTargetLine(row({ total_exposure_s: 0 })))
      .toContain("you haven't kept any of it yet");
  });

  // --- the same clause on a mosaic ------------------------------------------
  //
  // "what you already have on it" is read as "can I let this one go?", and on a
  // mosaic a target total is not that number. The season does not come round
  // again for a year, so a barely-started raster read as finished costs the
  // object rather than a sentence that can be corrected later.

  it("reads the hours per panel on a mosaic, and keeps the total", () => {
    // 10 h over a 2x2 no-overlap canvas (field_fulls 4.0, the figure
    // tests/webapp/test_stack_run_field_fulls.py pins end-to-end) is 2.5 h on a
    // typical panel — a target to keep shooting, not one to let go.
    const line = closingTargetLine(
      row({ total_exposure_s: 36000, field_fulls: 4.0 }));
    expect(line).toContain("you have about 2.5 h on a typical part of it");
    // Every fact the line carried is still on it: a row that looked like the app
    // had mislaid 7.5 h would be a new untruth in place of the old one.
    expect(line).toContain("(10 h in total, spread over about 4 fields of sky)");
    expect(line).toContain("about 3 weeks left");
    expect(line).toContain("last good night around");
  });

  it("does not retire a 12x8 raster on six minutes a panel", () => {
    // The owner's own shooting shape, and where the substitution is two orders
    // of magnitude: 10 h totalled over 96 fields of sky. "you have 10 h on it"
    // is the sentence that loses him the object.
    const line = closingTargetLine(
      row({ total_exposure_s: 36000, field_fulls: 96.0 }));
    expect(line).toContain("you have about 6 min on a typical part of it");
    expect(line).toContain("spread over about 96 fields of sky");
  });

  it("is byte-for-byte unchanged on a single field and on an older backend", () => {
    // The whole point of the fallback: no scale, a scale of exactly one, a
    // garbled one, and a sub-unity one (which would *inflate* the depth — the
    // direction that hides the bug) all keep today's sentence.
    const plain = closingTargetLine(row());
    expect(plain).toContain("you have 1.0 h on it");
    for (const field_fulls of [null, undefined, 1, 0.4, NaN, -3]) {
      expect(closingTargetLine(row({ field_fulls }))).toBe(plain);
    }
  });

  it("still says nothing has been kept, however wide the canvas", () => {
    // A mosaic with no kept integration must not read "about 0 s on a typical
    // part of it" — the zero case is answered before any scaling.
    expect(closingTargetLine(row({ total_exposure_s: 0, field_fulls: 9.0 })))
      .toContain("you haven't kept any of it yet");
  });
});

describe("closingHeadline", () => {
  it("says nothing at all when nothing is leaving", () => {
    // The ordinary answer for most of the year, and what keeps the card from
    // being one more always-on banner.
    expect(closingHeadline(plan([]))).toBeNull();
    expect(closingHeadline(null)).toBeNull();
    expect(closingHeadline(undefined)).toBeNull();
  });

  it("names the target when there is one, and the soonest when there are more", () => {
    expect(closingHeadline(plan([row()]))).toBe(
      "M 42 is on its way out of your sky — about 3 weeks left.");
    const many = closingHeadline(plan([
      row({ safe: "m_31", name: "M 31", weeks_left: 1 }),
      row(),
    ]));
    expect(many).toContain("2 of your targets");
    expect(many).toContain("M 31 first, about a week left");
  });

  it("counts what is leaving, not what the endpoint had room to send", () => {
    // The list is bounded so the card cannot grow without limit; `n_closing` is
    // exact. Counting the rows would quietly undercount the moment it bites.
    const truncated = { ...plan([row({ safe: "m_31", name: "M 31", weeks_left: 1 })]),
                        n_closing: 17 };
    const line = closingHeadline(truncated);
    expect(line).toContain("17 of your targets");
    expect(line).toContain("M 31 first, about a week left");
  });

  it("falls back to the list on a backend too old to send the count", () => {
    // `n_closing` is additive; without it the list *is* the total, which is the
    // behaviour every install had before it existed.
    expect(closingHeadline(plan([row()]))).toBe(
      "M 42 is on its way out of your sky — about 3 weeks left.");
    expect(closingHeadline({ ...plan([row(), row({ safe: "m_31" })]), n_closing: undefined }))
      .toContain("2 of your targets");
  });

  it("explains the consequence in seasons, not in degrees", () => {
    expect(CLOSING_WHY).toContain("next year");
    expect(CLOSING_WHY).not.toContain("30°");
  });
});

describe("closingUrgentSentence / urgentlyClosing", () => {
  it("keeps only the targets whose season ends within the urgent window", () => {
    const rows = [row({ safe: "a", weeks_left: 0 }), row({ safe: "b", weeks_left: 1 }),
                  row({ safe: "c", weeks_left: 4 })];
    expect(urgentlyClosing(plan(rows)).map((t) => t.safe)).toEqual(["a", "b"]);
    expect(urgentlyClosing(plan([row({ weeks_left: 2 })]))).toEqual([]);
  });

  it("says nothing at all unless something is genuinely about to go", () => {
    // The Dashboard slot is shown to somebody who came to look at their
    // pictures; spending it on something a month away is how a self-hiding note
    // becomes a banner.
    expect(closingUrgentSentence(plan([row({ weeks_left: 3 })]))).toBeNull();
    expect(closingUrgentSentence(plan([]))).toBeNull();
    expect(closingUrgentSentence(null)).toBeNull();
  });

  it("names the target, and counts the others in the same week", () => {
    expect(closingUrgentSentence(plan([row({ weeks_left: 0 })])))
      .toBe("This is your last week for M 42 — after that it's gone until next year.");
    expect(closingUrgentSentence(plan([row({ weeks_left: 1 })])))
      .toContain("M 42 has about a week of good nights left");
    const two = closingUrgentSentence(plan([
      row({ safe: "a", weeks_left: 0 }), row({ safe: "b", name: "M 31", weeks_left: 1 }),
    ]));
    expect(two).toContain("1 other target of yours is in the same week");
    const three = closingUrgentSentence(plan([
      row({ safe: "a", weeks_left: 0 }), row({ safe: "b", weeks_left: 1 }),
      row({ safe: "c", weeks_left: 1 }),
    ]));
    expect(three).toContain("2 other targets of yours are in the same week");
  });
});
