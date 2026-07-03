import { describe, expect, it } from "vitest";
import type { EditOp, OpInstance } from "../../api/client";
import { HEAVY_DEBOUNCE_MS, LIGHT_DEBOUNCE_MS, previewDebounceMs } from "./previewDebounce";

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
