import { describe, expect, it } from "vitest";
import { ADDED_OP_DEFAULTS, opStartParams, paramStartValue } from "./opDefaults";
import { opModified } from "./opModified";
import type { EditOp, StackOptionField } from "../../api/client";

const f = (over: Partial<StackOptionField>): StackOptionField => ({
  key: "k", label: "K", type: "float", group: "simple", default: 0,
  min: null, max: null, step: null, options: null, help: null, depends_on: null, ...over,
});

// The real `tone.stretch` schema's shape: its *engine* default is the manual asinh
// curve at black 0.35, which clips about half the sky to black.
const STRETCH: EditOp = {
  id: "tone.stretch", label: "Stretch", group: "tone", stage: "any",
  proxy_safe: true, is_stretch: true, help: null,
  params: [
    f({ key: "mode", type: "enum", default: "asinh", options: ["asinh", "stf"] }),
    f({ key: "stretch", default: 0.5, depends_on: "mode=asinh" }),
    f({ key: "black", default: 0.35, depends_on: "mode=asinh" }),
    f({ key: "target_bg", default: 0.2, depends_on: "mode=stf" }),
  ],
};

describe("opStartParams", () => {
  it("starts an added Stretch in STF at the schema's own sky level", () => {
    // STF at target_bg 0.20 is exactly the pipeline's no-stretch fallback, so
    // adding the op leaves the picture on screen unchanged.
    expect(opStartParams(STRETCH)).toEqual(
      { mode: "stf", stretch: 0.5, black: 0.35, target_bg: 0.2 });
  });

  it("is the bare schema defaults for every other op", () => {
    const sharpen: EditOp = { ...STRETCH, id: "detail.sharpen", is_stretch: false,
      params: [f({ key: "amount", default: 0.6 }), f({ key: "radius", default: 1.5 })] };
    expect(opStartParams(sharpen)).toEqual({ amount: 0.6, radius: 1.5 });
  });

  it("ignores an override the schema's options don't offer", () => {
    // A backend that dropped STF must not be handed a mode it would reject.
    const asinhOnly: EditOp = { ...STRETCH, params: [
      f({ key: "mode", type: "enum", default: "asinh", options: ["asinh"] })] };
    expect(paramStartValue(asinhOnly, asinhOnly.params[0])).toBe("asinh");
  });

  it("only ever overrides keys the engine actually has", () => {
    // Each override names a real op and a real param, so none silently no-ops.
    expect(Object.keys(ADDED_OP_DEFAULTS)).toEqual(["tone.stretch"]);
    expect(Object.keys(ADDED_OP_DEFAULTS["tone.stretch"])).toEqual(["mode"]);
  });
});

describe("opModified against the starting values", () => {
  const op = (params: Record<string, unknown>) =>
    ({ uid: "s1", id: "tone.stretch", enabled: true, params });

  it("reads a freshly added Stretch as unmodified", () => {
    expect(opModified(op(opStartParams(STRETCH)), STRETCH)).toBe(false);
  });

  it("reads a Stretch moved to asinh as tuned", () => {
    expect(opModified(op({ ...opStartParams(STRETCH), mode: "asinh" }), STRETCH)).toBe(true);
  });

  it("reads a Stretch with no mode key as asinh — what the engine fills in", () => {
    expect(opModified(op({ stretch: 0.5 }), STRETCH)).toBe(true);
  });
});
