/** Per-run focus chips for the stack-history list.
 *
 * The Target page already shows two "focus story" callouts for a target's
 * *newest* result — "✨ sharpest yet" (`sharpestYet`) and the "softer than usual
 * → check focus" coaching (`softerThanUsual`). But the History list shows *every*
 * past stack with its raw `stack_fwhm_px`, and a beginner won't eyeball that px
 * column to spot which nights had focus trouble (or which set a record). This
 * turns each history row's number into a legible chip, judged — like the newest
 * result is — against only that run's *own priors* (the runs shot before it), so
 * the focus story of a target across nights is readable at a glance without maths.
 *
 * Pure and calibration-free: it reuses the exact same relative, per-target
 * `sharpestYet` / `softerThanUsual` helpers (no absolute px bar, no per-camera
 * tuning), so it can't over-claim across Seestar models. Fail-safe by design —
 * a run with no measurement, no measured priors, or a result in the normal band
 * simply gets no chip (absent from the map).
 */

import { sharpestYet } from "./sharpestYet";
import { softerThanUsual } from "./softStars";

/** Which chip a history row earns: a new sharpness record, or softer-than-usual. */
export type FocusVerdict = "sharpest" | "soft";

interface RunLike {
  id?: number | null;
  timestamp_utc: string;
  stack_fwhm_px?: number | null;
}

/**
 * Map each run id to its focus chip, judged against only the runs shot *before*
 * it. `runs` must be **newest-first** (exactly what `listStackRuns` returns), so
 * for the run at index `i` the slice `runs.slice(i)` is `[thisRun, ...olderRuns]`
 * — precisely the newest-first shape `sharpestYet`/`softerThanUsual` expect
 * (element 0 = current, the rest = priors). "sharpest" wins when a run set a new
 * personal-best FWHM at the time; otherwise "soft" when it came out materially
 * softer than the target's usual up to that point. Runs with no verdict are
 * omitted from the map. Non-mutating.
 */
export function focusChips(
  runs: RunLike[] | null | undefined,
): Map<number, FocusVerdict> {
  const out = new Map<number, FocusVerdict>();
  if (!runs) return out;
  for (let i = 0; i < runs.length; i++) {
    const r = runs[i];
    if (r.id == null) continue;
    // This run plus every run older than it (newest-first ⇒ priors follow).
    const upTo = runs.slice(i);
    if (sharpestYet(upTo)) out.set(r.id, "sharpest");
    else if (softerThanUsual(upTo)) out.set(r.id, "soft");
  }
  return out;
}
