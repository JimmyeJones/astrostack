/**
 * Plain-language "time left" estimate for a running job, shown on the Jobs page.
 *
 * A beginner who drops a night's subs and kicks off a stack of thousands of
 * frames walks away — and the first thing they want on return (or before
 * deciding to wait) is *how much longer?* The backend already reports per-**step**
 * progress (`phase` + `done`/`total`), but a stack runs several steps and each
 * step restarts its own `done`/`total` (a two-pass sigma-clip stack, for
 * instance, streams every frame once per pass), so a naive whole-job estimate
 * from the job's start time would be wrong. Instead we estimate only the
 * **current step**, from the rate of progress observed since that step began,
 * and the Jobs page shows it right next to the step's name and count so it reads
 * unambiguously as "this step".
 *
 * Everything here is pure and division-guarded: a missing/empty/complete
 * observation yields `null` (no number shown), never a wrong number or a throw —
 * so a wrong guess can never erode trust, and the helpers are trivially testable.
 */

export interface EtaSample {
  /** The job's current step label (`job.phase`). */
  phase: string;
  /** Items in the current step (`job.total`); ≤ 0 means "no measurable step". */
  total: number;
  /** Items done in the current step (`job.done`). */
  done: number;
  /** Observation time, ms since epoch. */
  tMs: number;
}

/** True when `cur` belongs to a *different* step than `prev`, or the same step
 * restarted (its `done` went backwards) or changed size — i.e. the rate anchor
 * must be reset so we don't average across a step boundary. */
export function isNewPhase(prev: EtaSample, cur: EtaSample): boolean {
  return prev.phase !== cur.phase || cur.total !== prev.total || cur.done < prev.done;
}

/** The anchor (first observation of the current step) to measure the rate from:
 * (re-)anchor at `cur` whenever the step (re)started, otherwise keep `prev`. */
export function updateEtaAnchor(prev: EtaSample | null, cur: EtaSample): EtaSample {
  if (prev === null || isNewPhase(prev, cur)) return cur;
  return prev;
}

/** Seconds left in the current step, from the average rate since `anchor`.
 * `null` when there is nothing sensible to show: no step total, the step is
 * already complete, or no measurable progress/time has elapsed since `anchor`. */
export function phaseEtaSeconds(anchor: EtaSample, cur: EtaSample): number | null {
  if (cur.total <= 0 || cur.done >= cur.total) return null;
  const dDone = cur.done - anchor.done;
  const dMs = cur.tMs - anchor.tMs;
  if (dDone <= 0 || dMs <= 0) return null;
  const remaining = cur.total - cur.done;
  const etaMs = (remaining * dMs) / dDone;
  if (!Number.isFinite(etaMs) || etaMs < 0) return null;
  return etaMs / 1000;
}

/** Friendly duration: seconds rounded to 5 s (min 5 s), whole minutes, or
 * `h + min` — coarse on purpose so the readout doesn't jitter between polls. */
export function formatEtaSeconds(seconds: number): string {
  const sec = Math.max(0, Math.round(seconds));
  if (sec < 60) {
    const r = Math.max(5, Math.round(sec / 5) * 5);
    return `${r} sec`;
  }
  const mins = Math.round(sec / 60);
  if (mins < 60) return `${mins} min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

// Above this, an estimate is more likely a noisy early guess than useful — show
// nothing rather than an alarming "~9 h left" that corrects itself moments later.
const _ETA_MAX_SECONDS = 24 * 60 * 60;

/** The label shown next to a running step: `~2 min left`, `almost done`, or
 * `null` when no trustworthy estimate is available yet. */
export function etaLabel(anchor: EtaSample, cur: EtaSample): string | null {
  const s = phaseEtaSeconds(anchor, cur);
  if (s === null || s > _ETA_MAX_SECONDS) return null;
  if (s < 5) return "almost done";
  return `~${formatEtaSeconds(s)} left`;
}
