import { describe, expect, it } from "vitest";
import { previewScaleCaption } from "./previewScale";

describe("previewScaleCaption", () => {
  it("returns null for missing/undefined data", () => {
    expect(previewScaleCaption(undefined)).toBeNull();
    expect(previewScaleCaption(null)).toBeNull();
    expect(previewScaleCaption({})).toBeNull();
  });

  it("returns null when the preview is effectively full-res", () => {
    expect(previewScaleCaption({ proxy_scale: 1.0, proxy_width: 1200 })).toBeNull();
    expect(previewScaleCaption({ proxy_scale: 1.05, proxy_width: 1400 })).toBeNull();
  });

  it("names the proxy width and scale when meaningfully downscaled", () => {
    const cap = previewScaleCaption({ proxy_scale: 4.0, proxy_width: 1500 });
    expect(cap).toContain("1500 px");
    expect(cap).toContain("4.0×");
    expect(cap).toContain("full resolution");
  });

  it("falls back to a width-less caption when only the scale is known", () => {
    const cap = previewScaleCaption({ proxy_scale: 2.5 });
    expect(cap).toContain("downscaled");
    expect(cap).toContain("2.5×");
    expect(cap).not.toContain("px");
  });

  it("ignores non-finite scales", () => {
    expect(previewScaleCaption({ proxy_scale: NaN, proxy_width: 1500 })).toBeNull();
  });
});
