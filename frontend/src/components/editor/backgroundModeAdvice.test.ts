import { describe, expect, it } from "vitest";
import type { EditOp, ObjectInfo } from "../../api/client";
import {
  backgroundModeAdvice, backgroundModeOptionLabel,
} from "./backgroundModeAdvice";

const modeParam = (dflt: string) => ({
  key: "mode", label: "Mode", type: "enum", default: dflt,
  options: ["per_channel", "luminance"],
  option_labels: { per_channel: "Per channel", luminance: "Luminance" },
});

const SUBTRACT = {
  id: "background.subtract", label: "Background subtract", group: "background",
  stage: "linear", params: [modeParam("per_channel"),
    { key: "box_size", label: "Box size", type: "int", default: 128 }],
} as unknown as EditOp;

const GRADIENT = {
  id: "background.final_gradient", label: "Gradient removal", group: "background",
  stage: "linear", params: [modeParam("luminance")],
} as unknown as EditOp;

const SHARPEN = {
  id: "detail.sharpen", label: "Sharpen", group: "detail", stage: "nonlinear",
  params: [{ key: "amount", label: "Amount", type: "float", default: 0.5 }],
} as unknown as EditOp;

const NEBULA = {
  id: "M 42", name: "Orion Nebula", type: "nebula",
  background_mode_hint: { mode: "luminance", text: "server copy for the Stack form" },
} as unknown as ObjectInfo;

const GALAXY = {
  id: "M 31", name: "Andromeda", type: "galaxy", background_mode_hint: null,
} as unknown as ObjectInfo;

describe("backgroundModeAdvice", () => {
  it("advises Luminance on a big emission nebula's untouched subtract op", () => {
    // The op carries no `mode` param yet, so the schema default (per_channel)
    // is what it is actually running at — exactly the case worth flagging.
    const a = backgroundModeAdvice(NEBULA, SUBTRACT, {});
    expect(a?.mode).toBe("luminance");
    expect(a?.text).toContain("glowing gas");
    expect(a?.text).toContain("sky model");
  });

  it("names the gradient op's own model, not the sky model", () => {
    const a = backgroundModeAdvice(NEBULA, GRADIENT, { mode: "per_channel" });
    expect(a?.text).toContain("gradient model");
    expect(a?.text).not.toContain("sky model");
  });

  it("does not reuse the server's Stack-form wording", () => {
    // That sentence describes the per-frame flatten over each sub and calls
    // per-channel "the default" — both wrong for an already-stacked image and
    // for the gradient op, whose default is already luminance.
    const a = backgroundModeAdvice(NEBULA, SUBTRACT, {});
    expect(a?.text).not.toContain("server copy for the Stack form");
  });

  it("is silent once the op is already on the advised mode", () => {
    expect(backgroundModeAdvice(NEBULA, SUBTRACT, { mode: "luminance" })).toBeNull();
    // The gradient op defaults to luminance, so an untouched one never nags.
    expect(backgroundModeAdvice(NEBULA, GRADIENT, {})).toBeNull();
  });

  it("is silent for a target the catalog advice doesn't cover", () => {
    expect(backgroundModeAdvice(GALAXY, SUBTRACT, {})).toBeNull();
    expect(backgroundModeAdvice(null, SUBTRACT, {})).toBeNull();
    expect(backgroundModeAdvice(undefined, SUBTRACT, {})).toBeNull();
    // An older backend omits the field entirely.
    expect(backgroundModeAdvice({} as ObjectInfo, SUBTRACT, {})).toBeNull();
  });

  it("is silent for ops with no background mode to choose", () => {
    expect(backgroundModeAdvice(NEBULA, SHARPEN, {})).toBeNull();
    expect(backgroundModeAdvice(NEBULA, null, {})).toBeNull();
    expect(backgroundModeAdvice(NEBULA, undefined, {})).toBeNull();
  });

  it("stays silent rather than guess when the mode can't be resolved", () => {
    const noDefault = {
      ...SUBTRACT,
      params: [{ key: "mode", label: "Mode", type: "enum" }],
    } as unknown as EditOp;
    expect(backgroundModeAdvice(NEBULA, noDefault, {})).toBeNull();
    expect(backgroundModeAdvice(NEBULA, noDefault, null)).toBeNull();
  });

  it("tolerates a hint with no usable mode", () => {
    const odd = { background_mode_hint: { mode: "", text: "x" } } as unknown as ObjectInfo;
    expect(backgroundModeAdvice(odd, SUBTRACT, {})).toBeNull();
  });
});

describe("backgroundModeOptionLabel", () => {
  it("reads the label off the op's own schema", () => {
    expect(backgroundModeOptionLabel("luminance", SUBTRACT)).toBe("Luminance");
  });

  it("falls back to the raw value when the schema carries no label", () => {
    const bare = { ...SUBTRACT, params: [{ key: "mode", label: "Mode", type: "enum" }] };
    expect(backgroundModeOptionLabel("luminance", bare as unknown as EditOp))
      .toBe("luminance");
    expect(backgroundModeOptionLabel("luminance", null)).toBe("luminance");
  });
});
