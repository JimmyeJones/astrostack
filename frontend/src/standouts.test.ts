import { describe, expect, it } from "vitest";
import { libraryStandouts } from "./standouts";
import type { SummaryTarget } from "./api/client";
import { formatIntegration } from "./format";

function target(over: Partial<SummaryTarget> = {}): SummaryTarget {
  return {
    safe: "M42", name: "Orion Nebula", total_exposure_s: 3600,
    integration_hours: 1, n_frames_accepted: 60,
    thumbnail_url: "/api/targets/M42/thumbnail", ...over,
  };
}

describe("libraryStandouts", () => {
  it("keeps two cards when the two superlatives name different targets", () => {
    const longest = target({ safe: "NGC7000", name: "North America", total_exposure_s: 7200 });
    const most = target({ safe: "M42", n_frames_accepted: 120 });
    expect(libraryStandouts(longest, most, formatIntegration)).toEqual([
      {
        key: "longest", title: "Your biggest project", target: longest,
        detail: "2.0 h of integration",
      },
      {
        key: "most_imaged", title: "Most-imaged target", target: most,
        detail: "120 subs kept",
      },
    ]);
  });

  it("merges into one card when both name the same target", () => {
    // The usual case on a Seestar — fixed-length subs make "most integration"
    // and "most subs" nearly the same question — and the only case on a
    // one-target library, where the page used to show one picture twice.
    const t = target({ total_exposure_s: 7200, n_frames_accepted: 240 });
    const cards = libraryStandouts(t, { ...t }, formatIntegration);
    expect(cards).toHaveLength(1);
    expect(cards[0].key).toBe("both");
    expect(cards[0].target.safe).toBe("M42");
    // Both accolades and both figures survive the merge — nothing is dropped,
    // which is the whole constraint: the reader loses no fact and gains the one
    // two separate cards could never state.
    expect(cards[0].title).toBe("Your biggest project — and most-imaged");
    expect(cards[0].detail).toBe("2.0 h of integration · 240 subs kept");
  });

  it("renders whichever single standout the server knows", () => {
    const t = target();
    expect(libraryStandouts(t, null, formatIntegration))
      .toEqual([{
        key: "longest", title: "Your biggest project", target: t,
        detail: "1.0 h of integration",
      }]);
    expect(libraryStandouts(null, t, formatIntegration))
      .toEqual([{
        key: "most_imaged", title: "Most-imaged target", target: t,
        detail: "60 subs kept",
      }]);
  });

  it("says nothing at all when nothing has been imaged", () => {
    expect(libraryStandouts(null, null, formatIntegration)).toEqual([]);
    expect(libraryStandouts(undefined, undefined, formatIntegration)).toEqual([]);
  });

  it("counts one kept sub as a sub, not subs", () => {
    expect(libraryStandouts(null, target({ n_frames_accepted: 1 }), formatIntegration)[0].detail)
      .toBe("1 sub kept");
  });
});
