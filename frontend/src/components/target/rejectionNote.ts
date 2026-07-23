/** Plain-language note naming the outlier-rejection clean-up a stack performed.
 *
 * The per-pixel rejection pass quietly discards the satellite streaks, aeroplane
 * trails and cosmic-ray hits that cross individual subs — a beginner never sees
 * that work, they just get a clean picture. This turns the stored tally into a
 * reassuring, honest sentence for the one-click "Process target" result, right
 * where the finished image lands (the Target page's "How's my stack?" card shows
 * the same cue, but a walk-away user may never open it).
 *
 * Kept honest and consistent with the engine's `stackhealth.py`:
 *  - Only the *data-driven* κ-σ / drizzle fraction is a real "we found and
 *    removed N%" figure, and only inside a sane band (below the floor nothing was
 *    rejected; above the ceiling the clip is suspiciously large and κ may be
 *    eating real signal, so the cheerful cue stays silent).
 *  - `min-max` rejection is *structural* — it always drops the extreme sample per
 *    pixel — so it names only its guarantee, with no (misleading) percentage.
 *    This is the invisible save a small walk-away auto-stack makes (it auto-picks
 *    min/max below ~11 frames, where κ-σ is blind to a lone trail).
 *
 * Pure + threshold-driven so it's trivially unit-tested. Returns `null` when
 * there is no honest clean-up to name.
 */

// The κ-σ / drizzle rejection-fraction band in which the "we cleaned the trails"
// cue is honest — mirrors `stackhealth.py::_REJECTION_NOTE_{MIN,MAX}_FRACTION`
// (and the History "high, check κ" line).
export const REJECTION_NOTE_MIN_FRACTION = 0.0005; // 0.05% of samples
export const REJECTION_NOTE_MAX_FRACTION = 0.08; // 8%

/** Format a rejection fraction as a friendly percentage (mirrors the engine's
 * `_format_reject_pct`: at least one significant digit, never "0.0%"). */
export function formatRejectPct(fraction: number): string {
  const pct = fraction * 100;
  const digits = pct < 1 ? 2 : pct < 10 ? 1 : 0;
  return `${pct.toFixed(digits)}%`;
}

export function rejectionNote(
  mode: string | null | undefined,
  fraction: number | null | undefined,
  nFramesUsed?: number | null,
): string | null {
  const m = (mode ?? "").trim();
  if (m === "sigma-clip" || m === "drizzle-reject") {
    if (
      fraction == null ||
      !Number.isFinite(fraction) ||
      fraction < REJECTION_NOTE_MIN_FRACTION ||
      fraction >= REJECTION_NOTE_MAX_FRACTION
    ) {
      return null;
    }
    return (
      `Cleaned ~${formatRejectPct(fraction)} of pixels — passing satellites, ` +
      "planes and cosmic-ray hits were rejected, so they're not in your final image."
    );
  }
  if (m === "min-max-reject") {
    // Structural: no percentage. Add the small-stack context when we know it,
    // since that is exactly why a walk-away auto-stack picked this method.
    const few =
      nFramesUsed != null && Number.isFinite(nFramesUsed) && nFramesUsed > 0
        ? `Because only ${nFramesUsed} sub${nFramesUsed === 1 ? "" : "s"} ` +
          "stacked, AstroStack "
        : "AstroStack ";
    return (
      `${few}dropped the brightest and darkest value at each pixel, so a lone ` +
      "satellite or plane trail can't show up in your final image."
    );
  }
  return null;
}
