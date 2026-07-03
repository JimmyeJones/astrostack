import { describe, expect, it } from "vitest";
import { prependCoverageLeveling, LEVEL_COVERAGE_ID } from "./coverageLeveling";
import type { EditOp, OpInstance } from "../../api/client";

const LEVEL_SPEC: EditOp = {
  id: LEVEL_COVERAGE_ID, label: "Coverage leveling", group: "background",
  stage: "linear", proxy_safe: true, is_stretch: false, help: null,
  params: [{ key: "object_sigma", label: "Object σ", type: "float", group: "advanced",
             default: 2.0, min: 1, max: 5, step: 0.1, options: null, help: null,
             depends_on: null }],
};
const specs = { [LEVEL_COVERAGE_ID]: LEVEL_SPEC };

const gradient: OpInstance = {
  uid: "g1", id: "background.final_gradient", enabled: true, params: { mode: "luminance" },
};
const mkUid = () => "lc-uid";

describe("prependCoverageLeveling", () => {
  it("prepends a leveling pass with default params on a mosaic", () => {
    const out = prependCoverageLeveling([gradient], true, specs, mkUid);
    expect(out).toHaveLength(2);
    expect(out[0].id).toBe(LEVEL_COVERAGE_ID);
    expect(out[0].params).toEqual({ object_sigma: 2.0 });
    expect(out[0].enabled).toBe(true);
    // Runs before the preset's own ops.
    expect(out[1]).toBe(gradient);
  });

  it("leaves a single-field (non-mosaic) recipe unchanged", () => {
    const ops = [gradient];
    expect(prependCoverageLeveling(ops, false, specs, mkUid)).toBe(ops);
  });

  it("does not duplicate an existing leveling pass", () => {
    const withLevel: OpInstance[] = [
      { uid: "l0", id: LEVEL_COVERAGE_ID, enabled: true, params: { object_sigma: 3 } },
      gradient,
    ];
    expect(prependCoverageLeveling(withLevel, true, specs, mkUid)).toBe(withLevel);
  });

  it("degrades gracefully when the op isn't in the schema", () => {
    const ops = [gradient];
    expect(prependCoverageLeveling(ops, true, {}, mkUid)).toBe(ops);
  });

  it("never mutates the input array", () => {
    const ops = [gradient];
    const out = prependCoverageLeveling(ops, true, specs, mkUid);
    expect(ops).toHaveLength(1);
    expect(out).not.toBe(ops);
  });
});
