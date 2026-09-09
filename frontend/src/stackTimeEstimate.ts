import { formatEtaSeconds } from "./jobEta";
import type { StackEstimate } from "./api/client";

/**
 * "About how long will this take?" — the sentence on the Stack form.
 *
 * The Jobs page can already say how much longer a *running* stack has to go, but
 * the decision that needs a number comes before the button: it is late, a
 * night's subs are in, and "start it now or in the morning?" is exactly the
 * question the app was silent about. The backend answers it by measuring — the
 * median seconds-per-sub of this target's own comparable finished runs
 * (`seestack/stacktime.py`) — so everything left here is wording.
 *
 * Two rules, both about not overclaiming:
 *
 * - it says **what it is standing on** ("from your last 3 stacks of this
 *   target"), because a number with no provenance reads as a promise;
 * - it softens to *Roughly* when the run being sized is far bigger than the runs
 *   the rate was learned on — a rate measured on 40 subs projected onto 4,000 is
 *   an extrapolation, and saying so costs nothing.
 *
 * Returns `null` whenever there is nothing honest to say (no estimate, an older
 * backend that sends none, a nonsense duration), and the form then shows no line
 * at all rather than a hedged one.
 */

/** Beyond this multiple of the basis runs' size, the projection is called
 * "roughly" rather than "about". Deliberately generous: doubling a night's subs
 * is ordinary, and the per-sub rate really is close to linear — it is the
 * order-of-magnitude jump that deserves the softer word. */
export const FAR_EXTRAPOLATION = 4;

/** The wording used to describe the *whole* time a stack of `plannedFrames`
 * subs would take, or `null` when the estimate can't be shown. */
export function stackTimeLine(
  estimate: StackEstimate["time_estimate"] | undefined,
  plannedFrames: number,
): string | null {
  if (!estimate) return null;
  const { seconds, basis_runs: runs, basis_frames: basisFrames } = estimate;
  if (!Number.isFinite(seconds) || seconds <= 0 || runs <= 0) return null;
  const far = basisFrames > 0 && plannedFrames >= basisFrames * FAR_EXTRAPOLATION;
  const lead = far ? "Roughly" : "About";
  const basis = runs === 1
    ? "your last stack of this target"
    : `your last ${runs} stacks of this target`;
  return `${lead} ${formatEtaSeconds(seconds)} to run — from ${basis}.`;
}
