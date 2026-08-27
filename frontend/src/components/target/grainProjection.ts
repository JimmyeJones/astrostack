/** "Is more time worth it?" — answer a beginner's most common uncertainty from
 * *their own picture's* measured grain, not a generic per-object-type time goal.
 *
 * The Target page already answers "have I shot enough?" two ways, and neither
 * looks at the result:
 *   - `integrationReadiness` compares accumulated hours against a fixed goal by
 *     object type (Galaxy 6 h, Nebula 4 h, …). Its own comment calls those "a
 *     rough 'enough for a clean image', not a precise SNR target" — so it can
 *     tell a beginner "keep going" while the noise badge beside it already shows
 *     a clean stack, or "plenty" while the picture is still visibly grainy.
 *   - `noiseReductionHint` states the honest √N law, but from integration time
 *     alone — it never reads what the stack actually came out like.
 *
 * `integrationTrend` *does* read measured grain, but needs **two** stacks
 * spanning a real integration increase before it can fit a falloff exponent.
 * The beginner who has stacked once — the common case, and the one asking the
 * question hardest — gets nothing measured at all. This module is that gap: from
 * a single measured `(integration, noise σ)` point it projects the ideal
 * shot-noise curve forward and says, in plain words, how much more light the
 * picture actually needs.
 *
 * The physics is fixed, not a setting: stacking background noise falls as
 * σ ∝ 1/√t, so reaching a target σ takes `(σ_now/σ_target)²` times the light.
 * Doubling total time cuts grain ~29 %; quadrupling it halves the grain.
 *
 * ## Reconciling with the goal verdict rather than contradicting it
 * Low grain is *not* the same claim as "you have enough integration": more time
 * also pulls out fainter detail, which is what the per-type goal is really
 * about. So the clean-verdict copy deliberately says more time now buys **faint
 * detail** rather than a visibly cleaner background — true, and it agrees with
 * the "keep going to pull out fainter detail" sitting directly above it instead
 * of telling a beginner to abandon a half-shot galaxy.
 *
 * ## Where the "clean" bar comes from (it is not invented here)
 * `noise_sigma` is measured in units of the picture's own robust signal range
 * (`seestack/edit/noise.estimate_noise_sigma`), so it *is* comparable across
 * gain/exposure — but it has no absolute physical magnitude, so the two bars
 * below are anchored to numbers the project already stands behind rather than
 * picked to taste:
 *   - `CLEAN_SIGMA = 0.02` — the owner's own real deep stacks (271–787 frames of
 *     one target, the 2026-08 walk-away investigation in `docs/IMPROVEMENTS.md`)
 *     measured 0.015–0.020, and those were good pictures. So "at or below what a
 *     few hundred subs actually delivers" is the honest bar for *clean*.
 *   - `GRAINY_SIGMA = 0.05` — `seestack/edit/noise._SIGMA_FULL`, the σ at which
 *     the app's own denoise advisor already asks for its *strongest* cut. If the
 *     editor thinks a picture needs everything it has, "still grainy" is not a
 *     claim, it is what the app is already doing about it.
 * Between the two is the honest middle band ("some grain left"). No threshold
 * here changes any processing — they only choose which sentence is printed.
 *
 * Fail-safe by construction: returns `null` (say nothing) unless a *genuine*
 * finished stack carries both a positive integration and a finite σ. Never
 * throws, never mutates, and the projection is clamped (see
 * `MAX_HONEST_EXTRA_HOURS`) so a fluke reading can't quote a beginner a number
 * of hours no run of clear nights would ever deliver.
 */

import { integrationTrend } from "./integrationTrend";

/** At or below this measured σ the picture reads as clean — more light refines
 * it rather than rescuing it. See the module docstring for the provenance. */
export const CLEAN_SIGMA = 0.02;
/** At or above this σ the picture is still visibly grainy — the same bar the
 * editor's denoise advisor uses for its strongest suggestion. */
export const GRAINY_SIGMA = 0.05;
/** Past this many *extra* hours the honest answer is "not from here" rather than
 * a figure: 60 h is dozens of clear nights for a Seestar owner, and quoting
 * "about 190 more hours" reads as a taunt, not a plan. Gated on the extra hours
 * rather than the light multiple on purpose — 25× the light on a 20-minute
 * first attempt is a perfectly reachable evening, and should be quoted. */
export const MAX_HONEST_EXTRA_HOURS = 60;

export type GrainLevel = "clean" | "some" | "grainy";

export interface GrainProjection {
  /** Measured background-noise σ of the stack this projection is read from. */
  sigma: number;
  /** Integration behind that stack, in hours. */
  hours: number;
  level: GrainLevel;
  /** Total light needed to reach `CLEAN_SIGMA`, as a multiple of what's already
   * there (e.g. 4 = "four times the light"). `null` once already clean, or when
   * the extra hours run past `MAX_HONEST_EXTRA_HOURS`. */
  moreLightFactor: number | null;
  /** The extra hours implied by `moreLightFactor` (i.e. `hours × (factor − 1)`),
   * or `null` on the same two cases. */
  extraHours: number | null;
  /** True when reaching clean would take more than `MAX_HONEST_EXTRA_HOURS` of
   * extra light — the projection is real, but too far away to quote as a plan. */
  beyondReach: boolean;
  /** Extra hours that would *halve* the grain: 4× the light, so 3× what's
   * already there. Always finite and always worth stating. */
  hoursToHalve: number;
  /** Plain-language one-liner for the card. */
  sentence: string;
}

interface RunLike {
  total_exposure_s?: number | null;
  noise_sigma?: number | null;
  /** Genuine stack runs are reusable; an editor-export / combine run is not, and
   * its σ isn't measured on the same kind of image. */
  reusable?: boolean;
}

function measured(v: number | null | undefined): v is number {
  return v != null && Number.isFinite(v) && v > 0;
}

/** "45 min" / "1.6 h" / "12 h" — the same idiom `integrationTrend` prints. */
export function fmtHours(h: number): string {
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 10) return `${h.toFixed(1)} h`;
  return `${Math.round(h)} h`;
}

/** "2×" / "2.5×" — a light multiple, trimmed of a pointless ".0". */
function fmtFactor(f: number): string {
  return Number.isInteger(f) ? `${f}×` : `${f.toFixed(1)}×`;
}

/**
 * Project a target's measured grain forward from its deepest genuine stack.
 *
 * `runs` is the target's stack runs in any order. The deepest *genuine* run that
 * carries both a positive integration and a finite σ is used — deepest rather
 * than newest, because a later shallow re-stack of a subset is not the picture
 * the user is judging. Returns `null` when no such run exists.
 *
 * Non-mutating; safe to call with `null`/`undefined`/an empty list.
 */
export function grainProjection(
  runs: RunLike[] | null | undefined,
): GrainProjection | null {
  if (!runs) return null;
  let best: { t: number; sigma: number } | null = null;
  for (const r of runs) {
    // An editor-export / combine run (`reusable === false`) is excluded; a run
    // from a backend too old to report the flag is treated as genuine, which is
    // what every other consumer of these rows assumes.
    if (r.reusable === false) continue;
    if (!measured(r.total_exposure_s) || !measured(r.noise_sigma)) continue;
    const t = r.total_exposure_s as number;
    if (best === null || t > best.t) best = { t, sigma: r.noise_sigma as number };
  }
  if (best === null) return null;

  const hours = best.t / 3600;
  const sigma = best.sigma;
  const level: GrainLevel =
    sigma <= CLEAN_SIGMA ? "clean" : sigma >= GRAINY_SIGMA ? "grainy" : "some";

  // σ ∝ 1/√t, so the light needed to fall from σ to CLEAN_SIGMA is (σ/target)².
  // One decimal is as much precision as a projection from one point deserves.
  const factor = Math.round(Math.pow(sigma / CLEAN_SIGMA, 2) * 10) / 10;
  const extra = hours * (factor - 1);
  const beyondReach = level !== "clean" && extra > MAX_HONEST_EXTRA_HOURS;
  const quotable = level !== "clean" && !beyondReach;
  const moreLightFactor = quotable ? factor : null;
  const extraHours = quotable ? extra : null;
  // Halving the grain is always exactly 4× the light — 3× more than is there.
  const hoursToHalve = hours * 3;

  const now = fmtHours(hours);
  const grain = sigma.toFixed(3);
  let sentence: string;
  if (level === "clean") {
    // Deliberately not "you're done": see "Reconciling with the goal verdict".
    sentence =
      `Measured on your own picture: the background already looks clean at ` +
      `${now} (grain ${grain}). More time from here mostly buys fainter ` +
      `detail rather than a visibly cleaner picture — doubling your ${now} ` +
      `would take the grain down about 29 % more.`;
  } else if (beyondReach) {
    sentence =
      `Measured on your own picture: it's still grainy at ${now} (grain ` +
      `${grain}), and grain only falls with the square root of time — getting ` +
      `it clean from here would take dozens more clear nights. Longer subs, a ` +
      `darker sky, or a brighter target will get you there far sooner than ` +
      `more hours on this one.`;
  } else if (level === "some") {
    sentence =
      `Measured on your own picture: there's a little grain left at ${now} ` +
      `(grain ${grain}). About ${fmtFactor(factor)} the light in total — ` +
      `roughly ${fmtHours(extra)} more — would bring it down to a ` +
      `clean-looking result.`;
  } else {
    sentence =
      `Measured on your own picture: it's still grainy at ${now} (grain ` +
      `${grain}). About ${fmtFactor(factor)} the light in total — roughly ` +
      `${fmtHours(extra)} more — would bring it down to a clean-looking ` +
      `result. Grain falls with the square root of time, so each extra hour ` +
      `helps a little less than the last.`;
  }

  return {
    sigma, hours, level, moreLightFactor, extraHours, beyondReach,
    hoursToHalve, sentence,
  };
}

/**
 * The projection as the Target page's readiness card should show it.
 *
 * Identical to `grainProjection`, except it stays **silent** when the target's
 * own *measured* noise trend already says the stack has plateaued (gone
 * sky-limited). This projection assumes the ideal σ ∝ 1/√t curve — a fair
 * assumption from one point, but a fitted falloff read off two or more real
 * stacks beats an assumed one every time, and a plateaued target is precisely
 * where the assumption is wrong. Left to speak, it would promise "about 4× the
 * light would clean this up" a few centimetres from the `IntegrationTrendBadge`
 * saying more subs won't help — the exact contradiction the badge itself was
 * careful to avoid with the add-time coaching.
 *
 * Every other trend verdict ("improving"/"slowing") agrees with the projection,
 * so it speaks there as normal.
 */
export function cardGrainProjection(
  runs: RunLike[] | null | undefined,
): GrainProjection | null {
  if (integrationTrend(runs)?.level === "plateaued") return null;
  return grainProjection(runs);
}
