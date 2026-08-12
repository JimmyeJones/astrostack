/** "How many more clear nights?" — a plain-language ETA to a target's
 * integration goal, derived from the owner's *own* recent pace on that target.
 *
 * The readiness card ("Is it enough yet?") answers *where you stand* and the
 * "Plan your next night" card answers *when you can shoot next*. Neither answers
 * the question a beginner actually asks between them — *"so how much longer will
 * this take me?"* — because the honest answer isn't a clock time, it's a count of
 * clear nights, and only the target's own history knows how much a clear night
 * is worth to this owner (Seestar, this sky, this framing, this rejection rate).
 *
 * So: take the recent nights that actually added kept subs, use their *median*
 * kept integration as the pace, and divide the remaining goal gap by it. The
 * estimate is deliberately phrased in **clear nights** — the app can't promise
 * weather, and saying "3 nights" when it means "3 clear nights" would be the one
 * dishonest way to word this.
 *
 * Pure and I/O-free (no React) so every edge case can be pinned in isolation.
 */
import type { NightSummary } from "../api/client";
import { formatIntegration } from "../format";

/** How many recent productive nights the pace is taken over. Long enough that a
 * single short night doesn't dominate, short enough that a change of habit
 * (longer sessions, a new filter, better focus) shows up quickly. */
export const PACE_LOOKBACK_NIGHTS = 5;

/** Below this much kept integration a "night" is really a test frame or two, not
 * a session — counting it would drag the median down and inflate the ETA. */
const MIN_PRODUCTIVE_NIGHT_S = 120;

export interface ClearNightsEstimate {
  /** Whole clear nights still needed (≥1), or null when there's no usable pace
   *  and the estimate is an advisory instead of a number. */
  nights: number | null;
  /** Median kept integration per productive night, in seconds (0 when none). */
  paceSeconds: number;
  /** How many nights the pace was taken over. */
  nightsUsed: number;
  /** The one-line, plain-language sentence to render. */
  text: string;
}

/** Median of a non-empty list (mean of the middle two when even). */
function median(xs: number[]): number {
  const v = [...xs].sort((a, b) => a - b);
  const mid = v.length >> 1;
  return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2;
}

/**
 * Estimate the clear nights left to a target's integration goal.
 *
 * `gapSeconds` is the remaining goal gap (the readiness card's
 * `goalHours - hours`); `nights` is the target's night-by-night breakdown
 * **newest first**, exactly as `/api/targets/{safe}/nights` returns it.
 *
 * Returns null — say nothing rather than guess — when the goal is already met,
 * when there's no night history, or when fewer than two nights have really
 * accrued anything (one night is not a pace). The one non-numeric answer is the
 * all-duds case: recent nights recorded subs but kept essentially none of them,
 * where the useful thing to say is "check focus", not a division by ~zero.
 */
export function estimateClearNights(
  gapSeconds: number,
  nights: NightSummary[] | null | undefined,
): ClearNightsEstimate | null {
  if (!Number.isFinite(gapSeconds) || gapSeconds <= 0) return null;
  if (!nights || nights.length === 0) return null;

  // Nights that recorded subs at all, newest first — the honest denominator for
  // "did this owner's recent nights produce anything?".
  const withFrames = nights.filter((n) => n.n_frames > 0).slice(0, PACE_LOOKBACK_NIGHTS);
  if (withFrames.length < 2) return null;

  const productive = withFrames.filter(
    (n) => Number.isFinite(n.kept_exposure_s) && n.kept_exposure_s >= MIN_PRODUCTIVE_NIGHT_S,
  );

  if (productive.length === 0) {
    // Every recent night went out and came back with (next to) nothing kept.
    // There's no pace to divide by, and the actionable answer isn't an ETA.
    return {
      nights: null,
      paceSeconds: 0,
      nightsUsed: withFrames.length,
      text:
        `Your last ${withFrames.length} nights on this target kept almost nothing, ` +
        `so there's no pace to judge by yet — worth checking focus and framing ` +
        `before counting on more nights.`,
    };
  }
  // One good night among duds is data, not a pace — stay quiet rather than
  // project the whole remaining goal off a single session.
  if (productive.length < 2) return null;

  const paceSeconds = median(productive.map((n) => n.kept_exposure_s));
  const est = clearNightsFromPace(gapSeconds, paceSeconds);
  if (!est) return null;
  return { ...est, nightsUsed: productive.length };
}

/**
 * The arithmetic half of the estimate: how many more clear nights a `gapSeconds`
 * goal gap takes at a known `paceSeconds` per night, and the sentence for it.
 *
 * Split out because the pace can arrive two ways — derived here from a target's
 * night list (the Target page), or precomputed server-side over the whole library
 * (the Dashboard's "Target progress" overview, which can't fetch a night list per
 * target). Both then divide and phrase it *identically*, so the two screens can
 * never quote different ETAs for the same picture.
 *
 * Returns null when there's nothing to say: no gap left, or no usable pace.
 */
export function clearNightsFromPace(
  gapSeconds: number,
  paceSeconds: number | null | undefined,
): Omit<ClearNightsEstimate, "nightsUsed"> | null {
  if (!Number.isFinite(gapSeconds) || gapSeconds <= 0) return null;
  if (typeof paceSeconds !== "number" || !Number.isFinite(paceSeconds) || paceSeconds <= 0) {
    return null;
  }
  const nightsToGo = Math.max(1, Math.ceil(gapSeconds / paceSeconds));
  return {
    nights: nightsToGo,
    paceSeconds,
    text:
      `At your recent pace (~${formatIntegration(paceSeconds)} of kept subs per ` +
      `clear night), that's about ${nightsToGo} more clear ${nightWord(nightsToGo)}.`,
  };
}

/** "night" / "nights" — one word, one place, so every phrasing agrees. */
export function nightWord(n: number): string {
  return n === 1 ? "night" : "nights";
}
