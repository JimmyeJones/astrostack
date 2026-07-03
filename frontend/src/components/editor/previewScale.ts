// Pure helper: caption for the "the live preview is downscaled" hint.
//
// The editor's live preview always runs on a ≤1500 px proxy of what may be a
// 150 MP mosaic, so fine detail and sharpening read differently than the
// exported full-res image (even now that spatial ops are proxy-corrected). A
// small dimmed caption sets the right expectation and heads off "why does my
// export look different?" confusion.

export interface PreviewScaleInfo {
  proxy_scale?: number;
  proxy_width?: number;
}

// Returns the caption string, or null when the preview is effectively full-res
// (small stacks whose master already fits within the proxy budget) so we don't
// nag when there's nothing to explain.
export function previewScaleCaption(
  info: PreviewScaleInfo | undefined | null,
): string | null {
  if (!info) return null;
  const scale = info.proxy_scale;
  const width = info.proxy_width;
  if (typeof scale !== "number" || !Number.isFinite(scale)) return null;
  // Below ~1.05× the proxy is essentially the full image — no point warning.
  if (scale <= 1.05) return null;
  if (typeof width === "number" && Number.isFinite(width) && width > 0) {
    return `Preview shown at ${Math.round(width)} px — export renders at full resolution (${scale.toFixed(1)}× larger).`;
  }
  return `Preview is downscaled — export renders at full resolution (${scale.toFixed(1)}× larger).`;
}
