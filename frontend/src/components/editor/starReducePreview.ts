// Pure helper: caption for "the star-reduction preview isn't the export's strength".
//
// Star reduction shrinks stars with a morphological erosion whose footprint is a
// physical star size in full-res pixels, divided by proxy_scale for the
// decimated preview proxy. Morphology can't use a sub-pixel footprint — it
// rounds to whole pixels and clamps at one — and decimation eats the stars
// themselves, so on a heavily-decimated preview (a ≤1500 px view of a large
// mosaic/drizzle) the reduction the user sees is near, but not on, the export's.
//
// This caption used to claim the preview *over*-reduces. Measured across star
// sizes 1–4 and proxy steps 2–5 the ratio spans 0.63×–1.58× with no consistent
// sign at the default size — so on a beginner's own picture the advice pointed
// the wrong way about as often as the right one. It now states only what is
// true in every measurement: judge the final strength on the export. The backend
// flag keeps its original name (`star_reduce_preview_overstates`) for API
// compatibility. Advisory only.

export interface StarReducePreviewInfo {
  star_reduce_preview_overstates?: boolean;
}

// Returns the caption string when the current preview's star reduction won't
// match the export's, or null otherwise (no star-reduce op, or a full-res view).
export function starReduceDiffersCaption(
  info: StarReducePreviewInfo | undefined | null,
): string | null {
  if (!info || !info.star_reduce_preview_overstates) return null;
  return (
    "Star reduction looks different here — this downscaled preview can't shrink "
    + "the stars by exactly the amount the exported full-resolution image will. "
    + "Judge the final strength on the export."
  );
}
