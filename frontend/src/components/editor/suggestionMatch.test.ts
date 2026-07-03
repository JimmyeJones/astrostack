import { describe, expect, it } from "vitest";
import { matchesSuggestion } from "./suggestionMatch";

describe("matchesSuggestion", () => {
  it("matches an exactly-equal value", () => {
    expect(matchesSuggestion(2.2, 2.2, 0.1)).toBe(true);
  });

  it("matches within half the step tolerance", () => {
    expect(matchesSuggestion(2.24, 2.2, 0.1)).toBe(true); // |Δ|=0.04 ≤ 0.05
    expect(matchesSuggestion(2.16, 2.2, 0.1)).toBe(true);
  });

  it("does not match beyond half the step", () => {
    expect(matchesSuggestion(2.3, 2.2, 0.1)).toBe(false); // |Δ|=0.1 > 0.05
    expect(matchesSuggestion(1.5, 2.2, 0.1)).toBe(false);
  });

  it("requires exact match when the step is missing", () => {
    expect(matchesSuggestion(3, 3, null)).toBe(true);
    expect(matchesSuggestion(3.01, 3, null)).toBe(false);
    expect(matchesSuggestion(3, 3, 0)).toBe(true);
  });

  it("never matches a non-numeric or unset current value", () => {
    expect(matchesSuggestion(undefined, 2.2, 0.1)).toBe(false);
    expect(matchesSuggestion("2.2", 2.2, 0.1)).toBe(false);
    expect(matchesSuggestion(NaN, 2.2, 0.1)).toBe(false);
  });
});
