// Pure helper: caption for "the deconvolution preview understates the export".
//
// Deconvolution reverses a sub-pixel star blur. On a heavily-decimated preview
// proxy (a ≤1500 px view of a large mosaic/drizzle) that blur is smaller than
// one proxy pixel, so its Richardson-Lucy kernel collapses to a near-no-op and
// the preview shows far less sharpening than the full-res export actually
// applies. This is a fundamental limit of the decimated grid — the backend
// flags it on the histogram (`deconv_preview_understates`) and we caption it
// honestly rather than let the preview silently mislead. Advisory only.
//
// It used to stop at "the export applies it at full strength" — the exact shape
// `sharpenPreview.ts` closed in v0.445.3, on the identical mechanism. This op
// carries **Iterations** (1-50) and **Blur width** (0.5-5 px), so a reader who
// cannot see the effect has two knobs and no way to set them, and the obvious
// move is to turn the iterations up until the preview shows something — which
// saves a picture with ringing they never judged. The full-size check renders at
// `proxy_scale == 1`, where the kernel is the export's own, so it is the answer
// and it sits directly under this sentence.

import { FULL_SIZE_CHECK_LABEL } from "./loupe";

export interface DeconvPreviewInfo {
  deconv_preview_understates?: boolean;
}

// Returns the caption string when the current preview understates deconvolution,
// or null otherwise (no deconv op, or the proxy is fine at this scale).
export function deconvUnderstatesCaption(
  info: DeconvPreviewInfo | undefined | null,
): string | null {
  if (!info || !info.deconv_preview_understates) return null;
  return (
    "Deconvolution preview understates the effect — this downscaled preview "
    + "can't show the full star-sharpening, but the exported full-resolution "
    + `image applies it at full strength. "${FULL_SIZE_CHECK_LABEL}" to judge it `
    + "— turning the iterations up until it shows here would sharpen the saved "
    + "picture harder than you meant."
  );
}
