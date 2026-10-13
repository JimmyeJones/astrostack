import { describe, expect, it } from "vitest";
import type { EditOp, OpInstance } from "../../api/client";
import {
  HEAVY_DEBOUNCE_MS,
  HEAVY_RENDER_MS,
  LIGHT_DEBOUNCE_MS,
  SLOW_DEBOUNCE_MS,
  SLOW_RENDER_MS,
  previewDebounceMs,
  settleForRenderMs,
} from "./previewDebounce";

function op(id: string, enabled = true): OpInstance {
  return { uid: id, id, enabled, params: {} };
}

const specs: Record<string, EditOp> = {
  "tone.saturation": {
    id: "tone.saturation", label: "Saturation", group: "tone", stage: "nonlinear",
    proxy_safe: true, is_stretch: false, heavy: false, help: null, params: [],
  },
  "detail.denoise": {
    id: "detail.denoise", label: "Noise reduction", group: "detail", stage: "linear",
    proxy_safe: true, is_stretch: false, heavy: true, help: null, params: [],
  },
  "detail.deconvolve": {
    id: "detail.deconvolve", label: "Deconvolution", group: "detail", stage: "linear",
    proxy_safe: true, is_stretch: false, heavy: true, help: null, params: [],
  },
  // Simulate a spec that predates the `heavy` field (undefined, not false).
  "detail.sharpen": {
    id: "detail.sharpen", label: "Sharpen", group: "detail", stage: "nonlinear",
    proxy_safe: true, is_stretch: false, help: null, params: [],
  },
};

describe("previewDebounceMs", () => {
  it("uses the light debounce for an empty pipeline", () => {
    expect(previewDebounceMs([], specs)).toBe(LIGHT_DEBOUNCE_MS);
  });

  it("uses the light debounce when no heavy op is present", () => {
    expect(previewDebounceMs([op("tone.saturation")], specs)).toBe(LIGHT_DEBOUNCE_MS);
  });

  it("uses the heavy debounce when an enabled heavy op is present", () => {
    expect(previewDebounceMs([op("tone.saturation"), op("detail.denoise")], specs))
      .toBe(HEAVY_DEBOUNCE_MS);
  });

  it("ignores a disabled heavy op", () => {
    expect(previewDebounceMs([op("detail.deconvolve", false)], specs))
      .toBe(LIGHT_DEBOUNCE_MS);
  });

  it("treats a spec without a heavy field as light (graceful degrade)", () => {
    expect(previewDebounceMs([op("detail.sharpen")], specs)).toBe(LIGHT_DEBOUNCE_MS);
  });

  it("treats an op with no known spec as light", () => {
    expect(previewDebounceMs([op("unknown.op")], specs)).toBe(LIGHT_DEBOUNCE_MS);
  });
});

describe("settleForRenderMs", () => {
  it("has no opinion without a measurement", () => {
    expect(settleForRenderMs(undefined)).toBeUndefined();
    expect(settleForRenderMs(null)).toBeUndefined();
  });

  it("has no opinion about a measurement that cannot be one", () => {
    // A stubbed or coarse clock reports 0, a failed render reports nothing, and
    // NaN/Infinity must never become a `setTimeout` delay.
    expect(settleForRenderMs(0)).toBeUndefined();
    expect(settleForRenderMs(-5)).toBeUndefined();
    expect(settleForRenderMs(NaN)).toBeUndefined();
    expect(settleForRenderMs(Infinity)).toBeUndefined();
  });

  it("keeps the light settle for a render a beginner would call instant", () => {
    // The bundled single field renders the whole Auto recipe in 0.19-0.31 s.
    expect(settleForRenderMs(190)).toBe(LIGHT_DEBOUNCE_MS);
    expect(settleForRenderMs(310)).toBe(LIGHT_DEBOUNCE_MS);
  });

  it("steps up at a render around half a second — a small mosaic", () => {
    expect(settleForRenderMs(HEAVY_RENDER_MS - 1)).toBe(LIGHT_DEBOUNCE_MS);
    expect(settleForRenderMs(HEAVY_RENDER_MS)).toBe(HEAVY_DEBOUNCE_MS);
    expect(settleForRenderMs(730)).toBe(HEAVY_DEBOUNCE_MS);
  });

  it("steps up again for a render measured in seconds — the owner's mosaic", () => {
    expect(settleForRenderMs(SLOW_RENDER_MS - 1)).toBe(HEAVY_DEBOUNCE_MS);
    expect(settleForRenderMs(SLOW_RENDER_MS)).toBe(SLOW_DEBOUNCE_MS);
    expect(settleForRenderMs(2810)).toBe(SLOW_DEBOUNCE_MS);
  });

  it("is a ceiling, not a multiplier — the editor still has to feel alive", () => {
    expect(settleForRenderMs(30_000)).toBe(SLOW_DEBOUNCE_MS);
  });

  it("is a ladder, so a render's jitter cannot re-arm a pending settle", () => {
    // `useDebouncedValue` restarts a pending timer whenever `wait` changes, so
    // two renders of one picture must agree. 2.4 s and 3.1 s are the same rung.
    expect(settleForRenderMs(2400)).toBe(settleForRenderMs(3100));
  });
});

describe("previewDebounceMs with a measured render", () => {
  it("lengthens the settle for a slow picture carrying no heavy op at all", () => {
    // This is the owner's case: the one-click Auto recipe on a mosaic proxy
    // emits no `heavy` op, and renders in 2.81 s.
    const ops = [op("tone.saturation")];
    expect(previewDebounceMs(ops, specs)).toBe(LIGHT_DEBOUNCE_MS);
    expect(previewDebounceMs(ops, specs, 2810)).toBe(SLOW_DEBOUNCE_MS);
  });

  it("leaves a fast picture exactly where it was", () => {
    expect(previewDebounceMs([op("tone.saturation")], specs, 260))
      .toBe(LIGHT_DEBOUNCE_MS);
  });

  it("keeps the heavy op hint as a floor, never a cap", () => {
    // A fast render does not talk the editor out of settling for a heavy op...
    expect(previewDebounceMs([op("detail.denoise")], specs, 120))
      .toBe(HEAVY_DEBOUNCE_MS);
    // ...and a heavy op on a slow picture takes the slow rung, not its own.
    expect(previewDebounceMs([op("detail.denoise")], specs, 4000))
      .toBe(SLOW_DEBOUNCE_MS);
  });

  it("ignores a measurement from a disabled heavy op's pipeline the same way", () => {
    expect(previewDebounceMs([op("detail.deconvolve", false)], specs, 700))
      .toBe(HEAVY_DEBOUNCE_MS);
  });
});
