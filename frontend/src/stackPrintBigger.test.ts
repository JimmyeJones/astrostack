import { describe, expect, it } from "vitest";
import { printBiggerAction } from "./stackPrintBigger";

const OFF = { drizzle: false, scale: 1.5 };

describe("printBiggerAction", () => {
  it("says nothing when there is no plan, or nothing bigger to reach", () => {
    expect(printBiggerAction(null, OFF)).toBeNull();
    expect(printBiggerAction(undefined, OFF)).toBeNull();
    expect(printBiggerAction({ bigger_name: null, bigger_drizzle_scale: null }, OFF))
      .toBeNull();
  });

  it("names the lever and the paper it reaches, and sets both knobs together", () => {
    const action = printBiggerAction(
      { bigger_name: "A3", bigger_drizzle_scale: 1.4 }, OFF);
    expect(action).toEqual({
      label: "Use drizzle ×1.4 — prints at A3",
      // Both, in one object: the estimate query is keyed on each, so the caller
      // must be able to land them in a single state update.
      values: { drizzle: true, drizzle_scale: 1.4 },
    });
  });

  it("writes a whole scale the way the engine's own sentence does", () => {
    expect(printBiggerAction({ bigger_name: "A2", bigger_drizzle_scale: 2 }, OFF)?.label)
      .toBe("Use drizzle ×2 — prints at A2");
  });

  it("still offers a raise when drizzle is already on at a lower scale", () => {
    const action = printBiggerAction(
      { bigger_name: "A3", bigger_drizzle_scale: 1.8 },
      { drizzle: true, scale: 1.2 });
    expect(action?.values).toEqual({ drizzle: true, drizzle_scale: 1.8 });
  });

  it("refuses a button that would change nothing", () => {
    expect(printBiggerAction(
      { bigger_name: "A3", bigger_drizzle_scale: 1.4 },
      { drizzle: true, scale: 1.4 })).toBeNull();
  });

  it("refuses a half-filled plan rather than promising an unnamed paper", () => {
    expect(printBiggerAction({ bigger_name: "A3", bigger_drizzle_scale: null }, OFF))
      .toBeNull();
    expect(printBiggerAction({ bigger_name: null, bigger_drizzle_scale: 1.4 }, OFF))
      .toBeNull();
    expect(printBiggerAction({ bigger_name: "  ", bigger_drizzle_scale: 1.4 }, OFF))
      .toBeNull();
  });

  it("refuses a scale that isn't a usable number", () => {
    for (const scale of [0, -1, NaN, Infinity]) {
      expect(printBiggerAction({ bigger_name: "A3", bigger_drizzle_scale: scale }, OFF))
        .toBeNull();
    }
  });
});
