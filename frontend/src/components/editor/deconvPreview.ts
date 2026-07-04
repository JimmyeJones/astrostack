// Pure helper: caption for "the deconvolution preview understates the export".
//
// Deconvolution reverses a sub-pixel star blur. On a heavily-decimated preview
// proxy (a ≤1500 px view of a large mosaic/drizzle) that blur is smaller than
// one proxy pixel, so its Richardson-Lucy kernel collapses to a near-no-op and
// the preview shows far less sharpening than the full-res export actually
// applies. This is a fundamental limit of the decimated grid — the backend
// flags it on the histogram (`deconv_preview_understates`) and we caption it
// honestly rather than let the preview silently mislead. Advisory only.

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
    + "image applies it at full strength."
  );
}
