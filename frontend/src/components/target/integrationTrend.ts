/** "Is this target still improving, or has it plateaued?" — a data-driven read
 * on whether adding more integration time is still cutting noise.
 *
 * Stacking noise falls with the square root of integration time (σ ∝ 1/√t), so
 * early subs help a lot and late subs help less — but a beginner has no intuition
 * for *where they are* on that curve. They either quit a target too early (noisy
 * result) or pour more nights into one that stopped improving hours ago. The
 * History page already draws the raw noise-σ sparkline across a target's stacks,
 * but it gives no verdict on whether that line is still tracking the ideal √t or
 * has flattened into the sky-noise floor (sky-limited — more subs barely help).
 *
 * This turns the target's *own* measured runs into that verdict. It compares the
 * shallowest and deepest measured stacks by their real integration time (not
 * chronology — a later stack can use fewer subs) and reads off the effective
 * falloff exponent: ideal shot-noise-limited is 0.5; a sky-limited plateau tends
 * to ~0. Purely relative to the target's own history — no absolute "good" bar, no
 * per-camera calibration, so it can't false-claim across Seestar models.
 *
 * It reads each run's **per-pixel** integration, not the target's total: a
 * mosaic's canvas grows as its panels are shot, so more total light can buy a
 * wider picture rather than a deeper one, and fitting the falloff against the
 * total would call a growing mosaic sky-limited (see `perPixelSeconds`). A
 * single-field target is unaffected — there the two figures are the same number.
 *
 * Fail-safe: returns `null` (say nothing) unless there are at least two stacks
 * that both measured a noise σ *and* span a real integration increase — below
 * that there simply isn't enough signal to judge the trend honestly. A single
 * short stack is deliberately left to the existing "add more time" coaching
 * (`nextBestMove`), which this never duplicates.
 */

import { perPixel } from "./perPixel";

// The deepest measured stack must have at least this much more integration than
// the shallowest before the two are far enough apart to read a trend from. Two
// stacks of near-identical depth tell you nothing about the noise-vs-time slope,
// and their σ difference would be mostly measurement jitter.
export const MIN_TIME_RATIO = 1.5;
// Effective falloff exponent p (σ ∝ t^-p). At/above this the stack is still
// tracking close to the ideal √t (p = 0.5) — real gains remain.
export const IMPROVING_EXPONENT = 0.4;
// At/below this the noise has essentially stopped responding to more time — the
// sky-noise floor dominates (sky-limited); more subs won't help much.
export const PLATEAU_EXPONENT = 0.15;

export type IntegrationLevel = "improving" | "slowing" | "plateaued";

export interface IntegrationTrend {
  level: IntegrationLevel;
  /** The deepest measured stack's **total** integration, in hours — the figure
   * every other surface prints for that run. "Deepest" is decided on per-pixel
   * integration (see `perPixelSeconds`); on a single field the two are the same
   * number and the same run. */
  hoursNow: number;
  /** Measured falloff exponent (σ ∝ t^-exponent); ideal √t is 0.5. */
  exponent: number;
  /** Honest % noise reduction expected from doubling integration time. */
  percentCutIfDoubled: number;
  /** Plain-language one-liner for the card. */
  sentence: string;
}

interface RunLike {
  total_exposure_s?: number | null;
  noise_sigma?: number | null;
  /** How many single-frame field-fulls of sky *this run's* canvas covers (see
   * `webapp/field_fulls.py`). 1.0 / null / absent on a single field, ~4.0 on a
   * 2×2 mosaic. Read here so the trend is fitted against per-pixel integration
   * rather than the target's total — see `perPixelSeconds`. */
  field_fulls?: number | null;
}

/** The integration a *pixel* of this run's canvas actually received, in seconds.
 *
 * The noise a stack comes out with is a property of a pixel: it falls with the
 * square root of the light **that pixel** collected. On a single field that is
 * the run's whole integration, because every sub covers the whole canvas — which
 * is why this helper reads as a no-op there, and why the trend has been fitted
 * against `total_exposure_s` since it was written.
 *
 * A mosaic breaks that identity in the one direction that matters, because its
 * canvas **grows as its panels are shot**. A target whose first stack covered a
 * 2×2 raster and whose next covered 3×3 at the same per-panel depth has 2.25×
 * the total integration and the *same* grain — which the total-time fit reads as
 * "noise stopped falling as you added time", i.e. a sky-limited plateau, and the
 * badge then tells a beginner to move on from a mosaic that is only a few subs
 * deep everywhere. Dividing by the run's own field-fulls measures the depth
 * instead of the width, and the two runs above correctly come out as *no
 * increase to judge* rather than as a plateau.
 *
 * A missing/garbled figure, and anything at or below 1.0, both fall back to 1.0
 * — a scale below one would *inflate* the apparent depth, and the backend
 * already clamps for the same reason (`field_fulls_of_sky`). So an older backend
 * that sends no field reproduces the pre-field behaviour exactly. */
function perPixelSeconds(totalSeconds: number, fieldFulls: number | null | undefined): number {
  return perPixel(totalSeconds, fieldFulls);
}

function measured(v: number | null | undefined): v is number {
  return v != null && Number.isFinite(v) && v > 0;
}

function fmtHours(h: number): string {
  // "1.4 h" reads better than "84 min" for multi-hour totals; fall back to
  // minutes only for well-under-an-hour spans.
  if (h < 1) return `${Math.round(h * 60)} min`;
  return `${h.toFixed(1)} h`;
}

/**
 * Judge whether a target is still improving with more integration time.
 *
 * `runs` is the target's stack runs (order doesn't matter here — the trend is
 * read by integration time, not chronology). Returns `null` unless at least two
 * runs measured a noise σ and the deepest spans `MIN_TIME_RATIO`× the
 * shallowest **per-pixel** integration (`perPixelSeconds`, which is the run's
 * own total on every single-field target). Non-mutating.
 */
export function integrationTrend(
  runs: RunLike[] | null | undefined,
): IntegrationTrend | null {
  if (!runs) return null;
  const points = runs
    .filter((r) => measured(r.total_exposure_s) && measured(r.noise_sigma))
    .map((r) => ({
      // What the *fit* uses: the light one pixel of this run's canvas got.
      t: perPixelSeconds(r.total_exposure_s as number, r.field_fulls),
      // What the *sentence* names: the target's own total, the figure every
      // other surface prints ("2.3 h · 840 subs"). Saying "double your 3 h" of
      // a 12-hour mosaic would be arithmetic nobody could reconcile.
      totalT: r.total_exposure_s as number,
      sigma: r.noise_sigma as number,
    }));
  if (points.length < 2) return null;

  // Compare the shallowest vs deepest measured stack by per-pixel integration.
  let shallow = points[0];
  let deep = points[0];
  for (const p of points) {
    if (p.t < shallow.t) shallow = p;
    if (p.t > deep.t) deep = p;
  }
  const ratio = deep.t / shallow.t;
  if (ratio < MIN_TIME_RATIO) return null;  // not enough spread to judge

  const hoursNow = deep.totalT / 3600;

  // Effective falloff exponent p: σ_deep/σ_shallow = (t_deep/t_shallow)^-p, so
  // p = ln(σ_shallow/σ_deep) / ln(t_deep/t_shallow). Ideal √t → 0.5; a plateau
  // (noise flat or rising with time) → ≤ 0.
  const exponent = Math.log(shallow.sigma / deep.sigma) / Math.log(ratio);
  // For the "double your time" projection, only ever promise a real, non-negative
  // gain, capped at the ideal √t reduction (~29%) so we never over-claim.
  const pClamped = Math.min(0.5, Math.max(0, exponent));
  const percentCutIfDoubled = Math.round((1 - Math.pow(2, -pClamped)) * 100);

  let level: IntegrationLevel;
  if (exponent >= IMPROVING_EXPONENT) level = "improving";
  else if (exponent <= PLATEAU_EXPONENT) level = "plateaued";
  else level = "slowing";

  const now = fmtHours(hoursNow);
  let sentence: string;
  if (level === "improving") {
    sentence =
      `Your noise is still falling close to the ideal (with the square root of ` +
      `time) as you add subs — this target is still improving, so more clear ` +
      `nights will keep making it cleaner (about ${percentCutIfDoubled}% cleaner ` +
      `again if you double your ${now}).`;
  } else if (level === "slowing") {
    sentence =
      `Your noise is still dropping, but slower than the ideal — you're past the ` +
      `steep part of the curve at ${now}. More subs still help a little (about ` +
      `${percentCutIfDoubled}% cleaner if you double your time), but the big gains ` +
      `are behind you.`;
  } else {
    sentence =
      `Your noise has stopped dropping even as you added time (${now} in) — this ` +
      `target looks sky-limited from here, so more subs won't help it much. A ` +
      `darker sky or a brighter target will do more than extra time on this one.`;
  }

  return { level, hoursNow, exponent, percentCutIfDoubled, sentence };
}
