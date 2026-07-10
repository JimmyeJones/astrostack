// Pure helper: caption for "the star-reduction preview overstates the export".
//
// Star reduction shrinks stars with a morphological erosion whose footprint is a
// physical star size in full-res pixels, divided by proxy_scale for the
// decimated preview proxy. Morphology can't use a sub-pixel footprint, so on a
// heavily-decimated preview (a ≤1500 px view of a large mosaic/drizzle) the star
// collapses below one proxy pixel and the footprint clamps up to 1 px —
// physically larger than the export's — so the preview shrinks stars *more* than
// the full-res export will. This is a fundamental limit of the decimated grid
// (and the opposite direction of the deconvolution caption): the backend flags
// it on the histogram (`star_reduce_preview_overstates`) and we caption it
// honestly so a user doesn't under-set the amount. Advisory only.

export interface StarReducePreviewInfo {
  star_reduce_preview_overstates?: boolean;
}

// Returns the caption string when the current preview overstates star reduction,
// or null otherwise (no star-reduce op, or the proxy is fine at this scale).
export function starReduceOverstatesCaption(
  info: StarReducePreviewInfo | undefined | null,
): string | null {
  if (!info || !info.star_reduce_preview_overstates) return null;
  return (
    "Star reduction preview overstates the effect — this downscaled preview "
    + "shrinks the stars more than the exported full-resolution image will, so "
    + "the export keeps them a little larger. Judge the final strength on the export."
  );
}
