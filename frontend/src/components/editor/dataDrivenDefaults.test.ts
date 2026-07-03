import { describe, expect, it } from "vitest";
import { applyDataDrivenDefaults, countDataDrivenDefaults } from "./dataDrivenDefaults";
import type { OpInstance } from "../../api/client";

const ops = (): OpInstance[] => [
  { uid: "s1", id: "detail.sharpen", enabled: true, params: { radius: 2.0, amount: 1 } },
  { uid: "d1", id: "detail.denoise", enabled: true, params: { strength: 0.5 } },
  { uid: "t1", id: "tone.stretch", enabled: true, params: { stretch: 0.6 } },
];

const SUG = {
  "detail.sharpen": { param: "radius", value: 3.5 },
  "detail.denoise": { param: "strength", value: 0.8 },
  "stars.reduce": { param: "size", value: 4 }, // not present in the pipeline
};

describe("applyDataDrivenDefaults", () => {
  it("seeds each present op's data-driven param from its suggestion", () => {
    const out = applyDataDrivenDefaults(ops(), SUG);
    expect(out[0].params).toEqual({ radius: 3.5, amount: 1 }); // other params kept
    expect(out[1].params).toEqual({ strength: 0.8 });
    expect(out[2].params).toEqual({ stretch: 0.6 }); // no suggestion → unchanged
  });

  it("leaves ops already at the suggested value untouched (no new object)", () => {
    const input = ops();
    input[0].params.radius = 3.5; // already at the suggestion
    const out = applyDataDrivenDefaults(input, SUG);
    expect(out[0]).toBe(input[0]); // unchanged reference
    expect(out[1]).not.toBe(input[1]); // denoise still diverges → replaced
  });

  it("does not mutate the input ops", () => {
    const input = ops();
    applyDataDrivenDefaults(input, SUG);
    expect(input[0].params.radius).toBe(2.0);
    expect(input[1].params.strength).toBe(0.5);
  });
});

describe("countDataDrivenDefaults", () => {
  it("counts only present ops whose value differs from the suggestion", () => {
    expect(countDataDrivenDefaults(ops(), SUG)).toBe(2);
  });

  it("is zero when every present op already matches", () => {
    const input = ops();
    input[0].params.radius = 3.5;
    input[1].params.strength = 0.8;
    expect(countDataDrivenDefaults(input, SUG)).toBe(0);
  });

  it("is zero when no suggestion applies to any present op", () => {
    expect(countDataDrivenDefaults(ops(), { "stars.reduce": { param: "size", value: 4 } })).toBe(0);
  });
});
