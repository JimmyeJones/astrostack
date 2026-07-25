/** "Softer than usual" — a per-target relative star-sharpness signal.
 *
 * Every finished stack stamps its own measured median star size
 * (`stack_fwhm_px`, native-frame pixels — *lower = sharper*, and comparable
 * across a target's runs since it's normalised for drizzle; v0.194.0). The
 * "✨ sharpest yet" beat (`sharpestYet`) already celebrates a new personal best;
 * this is the honest flip side — when a fresh stack came out *softer* than this
 * target's own norm, the most useful thing a beginner can do is check focus
 * before the next session.
 *
 * Reading a raw FWHM in pixels as "soft" against an absolute bar would need the
 * frame's arcsec/px, which varies by Seestar model (S30 vs S50) — so instead we
 * compare a run only against the target's *own* recent history (same camera,
 * same pixel scale), which needs no per-camera calibration and can't false-nag
 * across models. "Usual" is the **median** of the target's prior measured runs
 * (robust to a single flukey night), and we only speak up when the newest run is
 * materially worse than that median, with enough prior runs to make "usual"
 * meaningful. Fail-safe by design: it returns `null` (say nothing) on the first
 * run, when measurements are missing, or when the newest result is in the normal
 * band — better to stay quiet than nag on ordinary seeing variation.
 */

// The newest run must be at least this fraction softer (larger FWHM) than the
// target's usual to count as a genuine "check your focus" signal. Star size
// swings a fair amount night-to-night with seeing/altitude, so require a clear
// margin — 25% larger than the median prior — before advising a refocus, so
// ordinary variation never triggers it.
export const SOFT_STAR_MARGIN = 0.25;
// "Usual" needs a real baseline, not one data point: require at least this many
// prior runs with a measured FWHM before a median is trustworthy enough to judge
// the newest run against. Below this we stay silent.
export const SOFT_STAR_MIN_PRIORS = 2;

export interface SoftStars {
  /** The newest run's own median star size (native-frame pixels, lower = sharper). */
  currentFwhmPx: number;
  /** The target's usual star size (median of prior measured runs). */
  typicalFwhmPx: number;
}

interface RunLike {
  stack_fwhm_px?: number | null;
}

function measured(v: number | null | undefined): v is number {
  return v != null && Number.isFinite(v) && v > 0;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * Decide whether the newest stack's stars are softer than usual for a target.
 *
 * `runs` is the target's stack runs **newest-first** (exactly what
 * `listStackRuns` returns), so the current result is `runs[0]` and its priors
 * are `runs.slice(1)`. Returns a `SoftStars` only when the current run has a
 * measured FWHM, at least `SOFT_STAR_MIN_PRIORS` prior runs also measured one,
 * and the current FWHM is larger than the median prior by at least
 * `SOFT_STAR_MARGIN`. Otherwise `null` (nothing to flag).
 */
export function softerThanUsual(runs: RunLike[] | null | undefined): SoftStars | null {
  if (!runs || runs.length < 1) return null;
  const current = runs[0];
  if (!measured(current.stack_fwhm_px)) return null;

  const priorMeasured = runs
    .slice(1)
    .map((r) => r.stack_fwhm_px)
    .filter(measured);
  if (priorMeasured.length < SOFT_STAR_MIN_PRIORS) return null;

  const typical = median(priorMeasured);
  // Only speak up when materially softer than usual — never on a hair's-breadth
  // difference (that's just seeing jitter, not a focus problem).
  if (current.stack_fwhm_px <= typical * (1 + SOFT_STAR_MARGIN)) return null;

  return { currentFwhmPx: current.stack_fwhm_px, typicalFwhmPx: typical };
}
