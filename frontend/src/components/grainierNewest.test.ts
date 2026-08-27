import { describe, expect, it } from "vitest";
import { grainierGap } from "./grainierNewest";

describe("grainierGap", () => {
  it("says an ordinary gap as a percentage — where nearly every firing lands", () => {
    // The endpoint's own bar is ~17.6%, so this is the band that matters.
    expect(grainierGap(18)).toEqual({
      amount: "about 18% more background grain", joiner: "than",
    });
    expect(grainierGap(50).amount).toBe("about 50% more background grain");
    // Right up to the switch-over, inclusive of the band below it.
    expect(grainierGap(199).joiner).toBe("than");
  });

  it("says a large gap as a multiple, with the joiner the phrasing needs", () => {
    expect(grainierGap(2400)).toEqual({
      amount: "about 25.0× as much background grain", joiner: "as",
    });
    // A tripling is the switch-over point.
    expect(grainierGap(200)).toEqual({
      amount: "about 3.0× as much background grain", joiner: "as",
    });
    expect(grainierGap(320).amount).toBe("about 4.2× as much background grain");
  });
});
