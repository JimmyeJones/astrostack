// Pure helper: caption for "the sharpen preview understates the export".
//
// Sharpen's radius is a *full-resolution* pixel measure, which the op correctly
// shrinks by proxy_scale on the decimated preview proxy so the preview sharpens
// the same physical detail. Once that shrunken radius goes sub-pixel, though, the
// unsharp mask's Gaussian collapses towards the identity and the preview shows
// only a fraction of the local contrast the full-res export adds — measured at
// ~19 % for Auto's own 1.5 px radius on a step-4 mosaic proxy, and 0 % by step 6.
// Same fundamental limit of the decimated grid as deconvolution, and the same
// answer: the backend flags it on the histogram (`sharpen_preview_understates`)
// and we caption it honestly rather than let the preview quietly mislead.
// Advisory only.

export interface SharpenPreviewInfo {
  sharpen_preview_understates?: boolean;
}

// Returns the caption string when the current preview understates sharpening, or
// null otherwise (no sharpen op, or the radius is large enough at this scale).
export function sharpenUnderstatesCaption(
  info: SharpenPreviewInfo | undefined | null,
): string | null {
  if (!info || !info.sharpen_preview_understates) return null;
  return (
    "Sharpening preview understates the effect — at this radius the downscaled "
    + "preview can't show the fine detail being sharpened, but the exported "
    + "full-resolution image applies it at full strength. Raise the radius if you "
    + "want to judge it here."
  );
}
