import { describe, expect, it } from "vitest";
import type { StackOptionField } from "../api/client";
import {
  ENGINE_STACK_PLACEMENT, stackPlacementMismatches,
} from "./stackOptionPlacement";

function field(over: Partial<StackOptionField> & { key: string }): StackOptionField {
  return {
    label: over.key, type: "bool", group: "simple", default: false,
    min: null, max: null, step: null, options: null, help: null, depends_on: null,
    ...over,
  } as StackOptionField;
}

describe("stack option placement guard", () => {
  it("carries the engine's real descriptors, not an empty stub", () => {
    // A silently empty snapshot would make every check below vacuous.
    expect(Object.keys(ENGINE_STACK_PLACEMENT).length).toBeGreaterThan(20);
    // Drizzle is on the *simple* pane — the drift this guard was built to catch.
    expect(ENGINE_STACK_PLACEMENT.drizzle.group).toBe("simple");
    expect(ENGINE_STACK_PLACEMENT.drizzle_scale.group).toBe("advanced");
  });

  it("passes fixtures that place their fields where the engine does", () => {
    expect(stackPlacementMismatches([
      field({ key: "sigma_clip" }),
      field({ key: "sigma_kappa", type: "float", depends_on: "sigma_clip" }),
      field({ key: "drizzle" }),
    ])).toEqual([]);
  });

  it("catches a field hidden behind the Advanced accordion the app doesn't use", () => {
    const [problem] = stackPlacementMismatches([field({ key: "drizzle", group: "advanced" })]);
    expect(problem).toContain("drizzle");
    expect(problem).toContain("advanced");
    expect(problem).toContain("simple");
  });

  it("catches a wrong control type", () => {
    const [problem] = stackPlacementMismatches([
      field({ key: "sigma_kappa", type: "bool" }),
    ]);
    expect(problem).toContain("sigma_kappa");
    expect(problem).toContain("float");
  });

  it("catches a dependency the fixture gets wrong", () => {
    // The set models `sigma_clip`, so it *could* express the gate — declaring a
    // different one (or none) hides that the app greys this control out.
    const wrong = stackPlacementMismatches([
      field({ key: "sigma_clip" }),
      field({ key: "sigma_kappa", type: "float", depends_on: "drizzle" }),
    ]);
    expect(wrong).toHaveLength(1);
    expect(wrong[0]).toContain("sigma_clip");

    const missing = stackPlacementMismatches([
      field({ key: "sigma_clip" }),
      field({ key: "sigma_kappa", type: "float" }),
    ]);
    expect(missing).toHaveLength(1);
    expect(missing[0]).toContain("sigma_kappa");
  });

  it("allows a partial fixture that omits the field a dependency is gated on", () => {
    // Without a `sigma_clip` control there is nothing to gate on, so rendering
    // the slider unconditionally is the honest simplification, not drift.
    expect(stackPlacementMismatches([field({ key: "sigma_kappa", type: "float" })]))
      .toEqual([]);
  });

  it("ignores keys the engine doesn't have", () => {
    // Fixtures for hypothetical fields are a legitimate way to exercise the
    // generic descriptor-driven rendering.
    expect(stackPlacementMismatches([
      field({ key: "not_a_real_option", type: "enum", group: "advanced" }),
    ])).toEqual([]);
  });

  it("reports every fixture's problems together", () => {
    expect(stackPlacementMismatches([
      field({ key: "drizzle", group: "advanced" }),
      field({ key: "quality_weighted", group: "advanced" }),
    ])).toHaveLength(2);
  });
});
