import { describe, expect, it } from "vitest";
import type { EditOp, StackOptionField } from "../api/client";
import {
  ENGINE_PLACEMENT, allPlacementMismatches, placementMismatches,
} from "./editorOpPlacement";

function param(over: Partial<StackOptionField> & { key: string }): StackOptionField {
  return {
    label: over.key, type: "float", group: "simple", default: 0,
    min: null, max: null, step: null, options: null, help: null, depends_on: null,
    ...over,
  } as StackOptionField;
}

function op(id: string, params: StackOptionField[]): EditOp {
  return {
    id, label: id, group: "tone", stage: "any",
    proxy_safe: true, is_stretch: false, help: null, params,
  };
}

describe("editor op placement guard", () => {
  it("carries the engine's real spec, not an empty stub", () => {
    // A silently empty snapshot would make every check below vacuous.
    expect(Object.keys(ENGINE_PLACEMENT).length).toBeGreaterThan(5);
    expect(ENGINE_PLACEMENT["tone.stretch"].highlights.group).toBe("advanced");
  });

  it("passes a fixture that places its params where the engine does", () => {
    expect(placementMismatches(op("tone.levels", [
      param({ key: "black" }), param({ key: "white" }), param({ key: "gamma" }),
    ]))).toEqual([]);
  });

  it("catches the group drift that shipped an invisible button (v0.240.1)", () => {
    const [problem] = placementMismatches(op("tone.stretch", [
      param({ key: "highlights", group: "simple" }),
    ]));
    expect(problem).toContain("tone.stretch.highlights");
    expect(problem).toContain("simple");
    expect(problem).toContain("advanced");
  });

  it("catches a wrong control type", () => {
    const [problem] = placementMismatches(op("tone.curves", [
      param({ key: "points", type: "float" }),
    ]));
    expect(problem).toContain("tone.curves.points");
    expect(problem).toContain("curve");
  });

  it("catches a dependency the fixture gets wrong", () => {
    // The fixture models `mode`, so it *could* express the gate — declaring a
    // different one (or none) hides that the app greys this control out.
    const wrong = placementMismatches(op("tone.stretch", [
      param({ key: "mode", type: "enum" }),
      param({ key: "stretch", depends_on: "mode=stf" }),
    ]));
    expect(wrong).toHaveLength(1);
    expect(wrong[0]).toContain("mode=asinh");

    const missing = placementMismatches(op("tone.stretch", [
      param({ key: "mode", type: "enum" }),
      param({ key: "stretch" }),
    ]));
    expect(missing).toHaveLength(1);
    expect(missing[0]).toContain("tone.stretch.stretch");
  });

  it("allows a partial fixture that omits the param a dependency is gated on", () => {
    // Without a `mode` control there is nothing to gate on, so rendering the
    // slider unconditionally is the honest simplification, not drift.
    expect(placementMismatches(op("tone.stretch", [param({ key: "stretch" })]))).toEqual([]);
  });

  it("ignores ops and params the engine doesn't have", () => {
    // Fixtures for hypothetical ops are a legitimate way to exercise the generic
    // descriptor-driven rendering.
    // Same op-relative key/type that *would* be flagged on a real op id.
    expect(placementMismatches(op("made.up", [param({ key: "points", type: "float" })])))
      .toEqual([]);
    expect(placementMismatches(op("tone.curves", [param({ key: "points", type: "float" })])))
      .toHaveLength(1);
    expect(placementMismatches(op("tone.levels", [param({ key: "not_a_real_key" })])))
      .toEqual([]);
  });

  it("reports every fixture's problems together", () => {
    expect(allPlacementMismatches([
      op("tone.stretch", [param({ key: "highlights", group: "simple" })]),
      op("tone.curves", [param({ key: "auto", type: "bool", group: "simple" })]),
    ])).toHaveLength(2);
  });
});
