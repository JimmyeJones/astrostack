import { describe, expect, it } from "vitest";
import { opModified } from "./opModified";
import type { EditOp, OpInstance, StackOptionField } from "../../api/client";

const field = (over: Partial<StackOptionField>): StackOptionField => ({
  key: "amount", label: "Amount", type: "float", group: "simple", default: 0.5,
  min: 0, max: 1, step: 0.1, options: null, option_labels: undefined,
  help: null, depends_on: null, ...over,
});

const spec = (params: StackOptionField[]): EditOp => ({
  id: "detail.sharpen", label: "Sharpen", group: "detail", stage: "nonlinear",
  proxy_safe: true, is_stretch: false, help: null, params,
});

const op = (params: Record<string, unknown>): OpInstance =>
  ({ uid: "u1", id: "detail.sharpen", enabled: true, params });

describe("opModified", () => {
  it("is false when every param sits at its schema default", () => {
    expect(opModified(op({ amount: 0.5 }), spec([field({})]))).toBe(false);
  });

  it("is false when a param is absent (renders as the default)", () => {
    expect(opModified(op({}), spec([field({})]))).toBe(false);
  });

  it("is false when a param is null (treated as the default)", () => {
    expect(opModified(op({ amount: null }), spec([field({})]))).toBe(false);
  });

  it("is true when a param differs from its default", () => {
    expect(opModified(op({ amount: 0.8 }), spec([field({})]))).toBe(true);
  });

  it("is true when any one of several params differs", () => {
    const s = spec([field({ key: "amount", default: 0.5 }),
      field({ key: "radius", default: 1.0 })]);
    expect(opModified(op({ amount: 0.5, radius: 2.0 }), s)).toBe(true);
  });

  it("ignores keys the schema doesn't define (stale params)", () => {
    expect(opModified(op({ amount: 0.5, bogus: 99 }), spec([field({})]))).toBe(false);
  });

  it("compares structured (curve) params by value", () => {
    const s = spec([field({ key: "curve", type: "curve",
      default: [[0, 0], [1, 1]] })]);
    expect(opModified(op({ curve: [[0, 0], [1, 1]] }), s)).toBe(false);
    expect(opModified(op({ curve: [[0, 0], [0.5, 0.7], [1, 1]] }), s)).toBe(true);
  });

  it("is false when the spec is unknown", () => {
    expect(opModified(op({ amount: 0.8 }), undefined)).toBe(false);
  });
});
