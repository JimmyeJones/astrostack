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
 *  - `min-max` rejection is *structural* — it drops the extreme sample per pixel
 *    wherever there is one to spare — so it names only its guarantee, with no
 *    (misleading) percentage. This is the invisible save a small walk-away
 *    auto-stack makes (it auto-picks min/max below ~11 frames, where κ-σ is blind
 *    to a lone trail).
 *  - …and *"wherever there is one to spare"* is the part this used to skip
 *    (corrected 2026-09-11, with v0.422.1's engine half). The drop needs three
 *    samples **on a pixel**: below that `MinMaxRejectAccumulator` averages them
 *    all in, so the guarantee is simply false there and the sentence is withheld
 *    rather than softened. The count that decides it is the *depth*, not the
 *    run's frame total — a mosaic's subs are spread across its panels — which is
 *    the same correction `thinStackWarning` took the same day, from the same
 *    `field_fulls` figure the Jobs payload already carries. On a single field
 *    depth *is* the frame count, so that wording is unchanged to the byte.
 *
 * Pure + threshold-driven so it's trivially unit-tested. Returns `null` when
 * there is no honest clean-up to name.
 */

import { fieldsOfSkyLabel, perPixel, spansMoreThanOneField } from "./perPixel";

// The κ-σ / drizzle rejection-fraction band in which the "we cleaned the trails"
// cue is honest — mirrors `stackhealth.py::_REJECTION_NOTE_{MIN,MAX}_FRACTION`
// (and the History "high, check κ" line).
export const REJECTION_NOTE_MIN_FRACTION = 0.0005; // 0.05% of samples
export const REJECTION_NOTE_MAX_FRACTION = 0.08; // 8%

// Samples that must land on ONE pixel before the min/max drop has a brightest
// and a darkest it can spare — mirrors `seestack/stack/stacker.py`'s
// `MIN_MAX_MIN_FRAMES`, which is the accumulator's own band boundary
// (`1 <= count < 3` falls through to the plain mean). Change them together;
// `tests/test_min_max_floor_mirror.py` fails if they drift.
export const MIN_MAX_MIN_SAMPLES = 3;

/** Format a rejection fraction as a friendly percentage: `<0.1%` for a sliver,
 * one decimal below 10%, whole percent above.
 *
 * This *is* the engine's `stackhealth._format_reject_pct` rule, and it now says
 * so with a guard rather than a comment — the two write the same sentence about
 * the same run on two screens, so the pair is pinned against
 * `rejectPct.cases.json` from both sides. It used to only claim to mirror it: at
 * a measured 0.5% this side printed "0.50%" where the health note printed
 * "0.5%", and at the bottom of the cue's own band "0.07%" against "<0.1%" — two
 * decimals of false precision on a figure already prefixed with "~".
 */
export function formatRejectPct(fraction: number): string {
  const pct = fraction * 100;
  if (pct < 0.1) return "<0.1%";
  if (pct < 10) return `${(Math.floor(pct * 10 + 0.5) / 10).toFixed(1)}%`;
  return `${Math.floor(pct + 0.5)}%`;
}

export function rejectionNote(
  mode: string | null | undefined,
  fraction: number | null | undefined,
  nFramesUsed?: number | null,
  /** How many single-frame field-fulls of sky the run's canvas covers
   * (`field_fulls` on the stack job's result). Omit / null / ≤1 on a single
   * field and on any caller that doesn't have the figure — the note is then
   * exactly what it has always been. */
  fieldFulls?: number | null,
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
    // since that is exactly why a walk-away auto-stack picked this method — but
    // read it per *pixel*. The reason min/max was picked is the panel depth, not
    // the target's total (`_resolve_auto_reject` sizes it from the thinnest
    // substantial panel), so "because only 21 subs stacked" under a four-panel
    // mosaic names a number that is neither the reason nor the depth.
    const known =
      nFramesUsed != null && Number.isFinite(nFramesUsed) && nFramesUsed > 0;
    const mosaic = spansMoreThanOneField(fieldFulls);
    const depth = !known
      ? null
      : mosaic
        ? Math.round(perPixel(nFramesUsed as number, fieldFulls))
        : (nFramesUsed as number);
    // Below the accumulator's own floor there is no brightest-and-darkest to
    // spare and nothing was dropped, so the guarantee is false — say nothing
    // rather than soften it. (The Jobs card's thin-stack warning covers this
    // depth too and wins there; this makes the helper honest on its own.)
    if (depth != null && depth < MIN_MAX_MIN_SAMPLES) return null;
    const few = depth == null
      ? "AstroStack "
      : mosaic
        // Name both figures, the way `thinStackWarning` does: a mosaic owner
        // told "only 6 subs" under a picture the same page says took 21 has
        // been told two things that can't both be true.
        ? `Your ${nFramesUsed} subs are spread across ` +
          `${fieldsOfSkyLabel(fieldFulls)} — with about ${depth} ` +
          `sub${depth === 1 ? "" : "s"} on each part of this picture, AstroStack `
        : `Because only ${depth} sub${depth === 1 ? "" : "s"} stacked, AstroStack `;
    return (
      `${few}dropped the brightest and darkest value at each pixel, so a lone ` +
      "satellite or plane trail can't show up in your final image."
    );
  }
  return null;
}
