/** "✨ Your sharpest yet" — a per-target personal-record beat on star sharpness.
 *
 * The app already keeps every stack run of a target (History), and since
 * v0.194.0 each finished run stamps its own measured median star size
 * (`stack_fwhm_px`, in native-frame pixels — *lower = sharper*, and comparable
 * across a target's runs since it's normalised for drizzle). But nothing tells a
 * beginner, on a *new* result, that it just came out sharper than any of their
 * previous stacks of that same target — they'd have to eyeball the History table
 * and compare FWHM numbers themselves, which a beginner won't.
 *
 * That "you set a new personal best" beat is one of the most motivating moments
 * in the hobby, and the raw material is already stored. This is a pure,
 * threshold-free comparison — it never judges a run against an absolute "good"
 * bar (which would need per-camera tuning); it only ever compares a target
 * against *its own* prior best, so it can't over-claim or false-alarm.
 *
 * Returns `null` unless the newest run strictly beats the sharpest prior run
 * (first run, no measurement, or no improvement → nothing, card hidden).
 */

// A run must be at least this fraction sharper than the prior best to count as a
// genuine record — a hair's-breadth difference is just measurement noise in the
// FWHM fit, not a real "sharpest yet", so require a small margin before we
// celebrate. 2% tighter stars is comfortably above the fit's run-to-run jitter.
export const SHARPEST_MARGIN = 0.02;

export interface SharpestYet {
  /** The newest run's own median star size (native-frame pixels, lower = sharper). */
  currentFwhmPx: number;
  /** The sharpest value among the target's prior runs (the record just beaten). */
  priorBestFwhmPx: number;
  /** ISO-8601 timestamp of the prior-best run, so the UI can date the record. */
  priorBestDate: string;
}

interface RunLike {
  timestamp_utc: string;
  stack_fwhm_px?: number | null;
}

function measured(v: number | null | undefined): v is number {
  return v != null && Number.isFinite(v) && v > 0;
}

/**
 * Decide whether the newest stack is a target's sharpest yet.
 *
 * `runs` is the target's stack runs **newest-first** (exactly what
 * `listStackRuns` returns), so the current result is `runs[0]` and its priors
 * are `runs.slice(1)`. Returns a `SharpestYet` only when the current run has a
 * measured FWHM, at least one prior run also has one, and the current is
 * strictly sharper than the best prior by at least `SHARPEST_MARGIN`. Otherwise
 * `null`.
 */
export function sharpestYet(runs: RunLike[] | null | undefined): SharpestYet | null {
  if (!runs || runs.length < 2) return null;
  const current = runs[0];
  if (!measured(current.stack_fwhm_px)) return null;

  // Sharpest (smallest) FWHM among the prior runs that actually measured one.
  let priorBest: RunLike | null = null;
  for (const r of runs.slice(1)) {
    if (!measured(r.stack_fwhm_px)) continue;
    if (priorBest == null || (r.stack_fwhm_px as number) < (priorBest.stack_fwhm_px as number)) {
      priorBest = r;
    }
  }
  if (priorBest == null || !measured(priorBest.stack_fwhm_px)) return null;

  // Strictly-better-by-a-margin only — never over-claim on a tie or noise.
  if (current.stack_fwhm_px >= priorBest.stack_fwhm_px * (1 - SHARPEST_MARGIN)) {
    return null;
  }
  return {
    currentFwhmPx: current.stack_fwhm_px,
    priorBestFwhmPx: priorBest.stack_fwhm_px,
    priorBestDate: priorBest.timestamp_utc,
  };
}
