import { describe, expect, it } from "vitest";
import type { MergeSuggestion } from "../api/client";
import {
  describeMergeSuggestion,
  mergeInto,
  mergeOutcomeMessage,
  mergeSources,
  mergeSuggestionSignature,
  mergeSuggestionTotalExposureS,
} from "./mergeSuggestions";

function suggestion(over: Partial<MergeSuggestion> = {}): MergeSuggestion {
  return {
    object_name: "Andromeda Galaxy",
    center_ra_deg: 10.685,
    center_dec_deg: 41.269,
    max_sep_arcmin: 1.2,
    targets: [
      { safe: "m31_n2", name: "M31 night 2", n_frames_accepted: 200, total_exposure_s: 2000 },
      { safe: "m31_n1", name: "M31 night 1", n_frames_accepted: 100, total_exposure_s: 1000 },
    ],
    ...over,
  };
}

describe("mergeSuggestionSignature", () => {
  it("is a stable, order-independent id of the member safes", () => {
    const a = suggestion();
    const b = suggestion({
      targets: [a.targets[1], a.targets[0]],  // reversed order
    });
    expect(mergeSuggestionSignature(a)).toBe(mergeSuggestionSignature(b));
    expect(mergeSuggestionSignature(a)).toBe("m31_n1|m31_n2");
  });
});

describe("mergeInto / mergeSources", () => {
  it("merges into the first (deepest) target and takes the rest as sources", () => {
    const s = suggestion();
    expect(mergeInto(s)).toBe("m31_n2");
    expect(mergeSources(s)).toEqual(["m31_n1"]);
  });
});

describe("mergeSuggestionTotalExposureS", () => {
  it("sums every member's accepted exposure", () => {
    expect(mergeSuggestionTotalExposureS(suggestion())).toBe(3000);
  });
});

describe("describeMergeSuggestion", () => {
  it("names the object and the combined integration", () => {
    const text = describeMergeSuggestion(suggestion());
    expect(text).toContain("These 2 targets");
    expect(text).toContain("(Andromeda Galaxy)");
    expect(text).toContain("50 min total");  // 3000 s
  });

  it("does not claim the targets were shot on separate nights", () => {
    // The backend clusters on plate-solved sky position alone and knows nothing
    // about *when* anything was shot — the old wording asserted a fact the
    // detection never established, on a nudge the owner was already mistrusting.
    const text = describeMergeSuggestion(suggestion());
    expect(text).not.toMatch(/night/i);
    expect(text).toContain("in separate folders");
  });

  it("drops the object clause when unnamed", () => {
    const text = describeMergeSuggestion(suggestion({ object_name: null }));
    expect(text).not.toContain("Andromeda");
    expect(text).toContain("the same object,");
  });

  it("drops the integration clause when there's no exposure", () => {
    const text = describeMergeSuggestion(
      suggestion({
        targets: [
          { safe: "a", name: "A", n_frames_accepted: 0, total_exposure_s: 0 },
          { safe: "b", name: "B", n_frames_accepted: 0, total_exposure_s: 0 },
        ],
      }),
    );
    expect(text).toContain("Combine them.");
    expect(text).not.toContain("total)");
  });
});

describe("mergeOutcomeMessage", () => {
  it("names the pictures that came with the folders, so the promise is checkable", () => {
    expect(mergeOutcomeMessage(2, "Andromeda Galaxy", 3)).toBe(
      "Combined 2 folders of Andromeda Galaxy into one deep target. " +
      "Your 3 existing pictures came with them — see History. " +
      "Re-stack it to get the deeper picture.",
    );
  });

  it("uses the singular for one picture", () => {
    expect(mergeOutcomeMessage(2, "M 31", 1)).toContain(
      "Your 1 existing picture came with it — see History.",
    );
  });

  it("says nothing extra when no folder had a picture", () => {
    expect(mergeOutcomeMessage(3, "M 31", 0)).toBe(
      "Combined 3 folders of M 31 into one deep target. " +
      "Re-stack it to get the deeper picture.",
    );
  });

  it("degrades to today's sentence on a backend that omits the count", () => {
    // Absent must read as "unknown", never as zero dressed up as a claim.
    const today = "Combined 3 folders of M 31 into one deep target. " +
      "Re-stack it to get the deeper picture.";
    expect(mergeOutcomeMessage(3, "M 31", undefined)).toBe(today);
    expect(mergeOutcomeMessage(3, "M 31", null)).toBe(today);
  });
});
