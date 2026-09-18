/** "To make this even better" — one calm, plain-language sentence naming the
 * single highest-leverage thing that would most improve this target next time.
 *
 * The app is full of *honest signals* about a finished stack — how many subs
 * combined, how many failed to plate-solve, the total integration time — but
 * they live scattered across the Target/History/QC surfaces as *numbers*, and
 * nothing tells a beginner the one thing to do differently. A non-expert who
 * shot only 15 minutes, or lost most of their subs to "not located", has no way
 * to know which lever matters most on *their* picture. That "what should I
 * change next?" is exactly the coaching a beginner wants and a pro does in their
 * head.
 *
 * This picks exactly ONE lever — the highest-priority unmet one, in a fixed sane
 * order (can't-locate-subs → too-thin → soft-stars → mostly-outside-the-picture
 * → short-integration → all-good) — and says it plainly, translating
 * counts/minutes into "install the star DB / add subs / refocus / shoot it wider
 * / add time" rather than a QC table. It never
 * judges star sharpness against an absolute bar (FWHM in pixels needs per-camera
 * calibration to read as "soft"); the soft-star rung fires only on a *relative*
 * signal — this target's newest stack being softer than its own history (see
 * `softStars.ts`) — so it can't false-alarm across camera models.
 *
 * Pure + threshold-driven so it's trivially unit-testable. Returns `null`
 * (card hidden) when there's no finished stack to advise on, when inputs are
 * missing, or when the result is already deep and healthy — never an error.
 */

import { THIN_STACK_MAX_FRAMES } from "./thinStack";
import {
  A_TYPICAL_PART,
  fieldsOfSkyLabel,
  perPixel,
  spansMoreThanOneField,
} from "./perPixel";
import { formatIntegration } from "../../format";
import { settingsLink } from "../../settingsSections";
import {
  goalDifficultyFactor,
  goalHoursForType,
  type GoalDifficulty,
} from "../../readiness";
import { objectTypeBucket } from "../../tonight";
import type { SoftStars } from "./softStars";
import type { GrainLevel } from "./grainProjection";

// A plate-solve shortfall is worth flagging as the top lever only when it's both
// a real share of the session AND several subs — a stray unsolved frame or two
// isn't worth a nudge, but losing a quarter-plus of your subs to "not located"
// is usually the single biggest thing holding the stack back (they never reach
// the stacker at all).
export const LOCATE_MIN_UNSOLVED = 3;
export const LOCATE_MIN_FRACTION = 0.25;

// Below ~1 hour a deep-sky target has barely started building signal-to-noise;
// galaxies and nebulae reward multiple hours.
//
// Both of these bars are **per-pixel** quantities — "how much light has landed
// where I am looking?" — so on a mosaic they are compared against the run's
// integration divided by the sky its canvas covers (`perPixel.ts`), not against
// the target's total. Read off the total, a 12x8 raster at 3 h is "genuinely
// deep" at under two minutes a panel, and the card goes silent on a picture
// whose single biggest lever is more time. A single field is unaffected: there
// the two figures are the same number.
export const SHORT_INTEGRATION_S = 60 * 60; // 1 hour
// At/above this the stack is genuinely deep; with a healthy frame count there's
// nothing to nudge, so stay silent rather than nag a good result.
export const DEEP_INTEGRATION_S = 3 * 60 * 60; // 3 hours

// …and those two numbers are not independent constants: they are the readiness
// card's own ladder boundaries, evaluated at its default goal. `readiness.ts`
// calls a target "a good start" below **0.25** of its goal and "nearly there"
// at **0.75**, and the goal for an unclassified/nebula target is **4 h** — so
// 0.25 x 4 h = 1 h is exactly `SHORT_INTEGRATION_S` and 0.75 x 4 h = 3 h is
// exactly `DEEP_INTEGRATION_S`. The ladder was written for that one bucket and
// then applied to every object, which is how the same page came to say two
// things about one target: a star cluster (goal 1.5 h) at 50 min was "nearly
// there" on the readiness card and "add more time — galaxies and nebulae reward
// hours, so another clear night or two" here, and a galaxy (goal 6 h) at 1.2 h
// was "a good start" there and "a solid result — plenty of subs went in" here.
//
// So express the bars where they came from: the same fractions of the same
// per-type goal `readiness.ts` and `mosaicEffort.ts` already judge against.
// Omitting the type yields the `Other` bucket's 4 h, i.e. 1 h / 3 h — today's
// numbers, bit for bit, for every caller that has no catalogue match.
export const SHORT_INTEGRATION_FRACTION = 0.25;
export const DEEP_INTEGRATION_FRACTION = 0.75;

/** The two per-pixel bars (seconds) this ladder judges `type` against.
 *
 * `difficulty` is the target's vetted "how hard for a Seestar?" verdict, passed
 * straight through to `goalHoursForType`: the bars are fractions of the goal, so
 * a goal the badge two inches up the page has sharpened has to carry them with
 * it — otherwise this ladder disagrees with the readiness card again, in the
 * other direction from the one v0.429.2 closed. Omit it and the bars are exactly
 * the per-type ones. */
export function integrationBars(
  type: string | null | undefined,
  difficulty?: GoalDifficulty,
): {
  shortS: number;
  deepS: number;
} {
  const goalS = goalHoursForType(type, difficulty) * 3600;
  return {
    shortS: goalS * SHORT_INTEGRATION_FRACTION,
    deepS: goalS * DEEP_INTEGRATION_FRACTION,
  };
}

// How much of the object has to be *missing* before capturing the rest of it
// outranks deepening the part you have.
//
// `FramingVerdictNote` sits an inch below this card and, on a `partial` verdict,
// prescribes a different next session: "shoot it in mosaic mode" / "adding more
// panels would capture the rest", against this card's "add more time" / "more
// passes over the same mosaic". Both are true; a beginner cannot act on both,
// and this card is the one whose docstring claims to name *the single*
// highest-leverage move — so it is the one that has to know about the other.
//
// The bar is two thirds captured, i.e. "a third or more of it is missing", and
// it is a judgement rather than a measurement, so here is the argument. A
// `partial` verdict only says the object cannot fit this canvas *at all* — it
// fires just as readily at 95 % captured (a nebula slightly wider than the
// frame, well centred), where the missing sliver is an outer edge and depth is
// plainly the better lever. Below two thirds the picture is of a *fragment* —
// what is missing is at least half as much again as what is there — and no
// amount of integration will ever bring it in, because it never reaches the
// sensor. The two photographed cases
// that filed this (a single field with 15 % of M42 in it; a 2x2 mosaic with
// 55 % of its object) both clear it comfortably, and the 95 % case the lead
// warned against stays silent.
//
// Deliberately NOT applied to the `clipped` verdict, whose fix is a better
// pointing: "re-centre it next session" and "shoot it for longer" are jointly
// satisfiable in one session, so those two cards do not compete.
export const FRAMING_MAX_COVERAGE = 0.67;

export type NextBestMoveKind =
  | "locate" | "thin" | "soft" | "framing" | "integration" | "good";

/** The measured framing verdict for the same run, as `/framing` serves it —
 *  structurally typed so the caller can hand over the response it already has.
 *  Every field is optional: an older backend, a run with no usable WCS, or a
 *  target that isn't a sized catalogue object all read as "no verdict", which
 *  leaves this ladder exactly what it was. */
export interface NextBestMoveFraming {
  level?: string | null;
  coverage?: number | null;
  /** The backend's own friendly integer for `coverage` — never re-rounded here,
   *  so the two cards cannot print two percentages of one measurement. */
  coverage_pct?: number | null;
  canvas?: string | null;
  object_name?: string | null;
}

export interface NextBestMove {
  kind: NextBestMoveKind;
  phrase: string;
  /** Where to go and do it, when the phrase names something that lives on
   * another screen — so "in Settings" is a tap rather than a hunt through seven
   * sections. Same shape as `StackHealthCard`'s `noteAction`. */
  action?: { label: string; href: string };
}

export interface NextBestMoveInput {
  /** Frames the latest stack actually combined (`StackRun.n_frames_used`). */
  nFramesUsed?: number | null;
  /** Total integration time in seconds (`StackRun.total_exposure_s`), if known. */
  integrationS?: number | null;
  /** Accepted subs that couldn't be plate-solved (the "unsolved" reject bucket). */
  nUnsolved?: number | null;
  /** Relative star-softness signal vs this target's own history, if computable
   * (from `softerThanUsual(runs)`). Present only when the newest stack came out
   * materially softer than usual; drives the "refocus" rung. */
  softStars?: SoftStars | null;
  /** How many single-frame field-fulls of sky the stack's canvas covers
   * (`StackRun.field_fulls`). Omit / null / ≤1 on a single field and on any
   * caller without the figure — the ladder is then exactly what it was. */
  fieldFulls?: number | null;
  /** The catalogue object type from the identify card ("Open Cluster",
   * "Galaxy", …), so the two time rungs are judged against the same per-type
   * goal the readiness card beside them uses, and the advice names the right
   * kind of object. Omit / null / unrecognised → the `Other` bucket, which is
   * today's 1 h / 3 h ladder exactly. */
  objectType?: string | null;
  /** The target's vetted difficulty verdict, when the caller has one — the same
   * `DifficultyHint` the badge on this page renders. It sharpens the per-type
   * goal the two rungs are fractions of (see `integrationBars`). Omit / null /
   * an un-curated verdict → today's per-type ladder, unchanged. */
  difficulty?: GoalDifficulty;
  /** `"uneven"` when a substantial part of this run's canvas was shot with fewer
   * subs than the rest and measures grainier for it — the backend's own
   * `seestack.stackhealth.grain_verdict`, already served on every run row. It is
   * `null` by construction on a single field and on an evenly covered mosaic (a
   * single field has no coverage levels to compare), and on an older backend —
   * all of which keep every phrase below byte-for-byte what it was. Read by the
   * `good` rung and — since v0.438.1, to scope the same claim the same way — by
   * the `integration` rung; see the comments there. */
  grainVerdict?: string | null;
  /** The *measured* grain of the picture the readiness card on this same page is
   * describing — `cardGrainProjection(runs)`'s own `level`, so the two cards
   * cannot come to different opinions about one picture. Only the `integration`
   * rung reads it, and only to choose which of two true things it offers as the
   * reason for adding time: a cleaner background (when the picture is not clean
   * yet) or fainter detail (when it already measures clean). Omit / null — no
   * finished stack with a measured σ, or an older backend — and every phrase is
   * byte-for-byte what it was. It never changes the rung that fires. */
  grainLevel?: GrainLevel | null;
  /** The measured framing verdict for the same run (`/framing`), so the ladder
   * knows about the lever the card an inch below it is naming. Only a `partial`
   * verdict under `FRAMING_MAX_COVERAGE` changes anything; omit / null / any
   * other verdict and every phrase below is byte-for-byte what it was. */
  framing?: NextBestMoveFraming | null;
}

function finite(v: number | null | undefined): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** True when the measured framing verdict says this picture holds only a
 * *fragment* of its object: `partial` — the one verdict whose fix is more sky
 * rather than a better pointing — at or under `FRAMING_MAX_COVERAGE`.
 *
 * Split out of `framingRung` because a second card on the same page now has to
 * ask the identical question: the readiness card prices "is it enough yet?"
 * against the canvas in front of it, which on a fragment is the canvas this
 * ladder has just said to stop shooting (see `readinessCanvasScope`). Two
 * surfaces disagreeing about whether a single field is the right canvas is the
 * very contradiction the rung exists to close, so they share one gate rather
 * than two copies of a constant.
 *
 * The rung asks for one thing more — the backend's own friendly percentage,
 * because its sentence *names* it — which is why that check stays there. The
 * scope clause names no number, so it does not need one.
 */
export function framingIsFragment(
  v: NextBestMoveFraming | null | undefined,
): boolean {
  if (!v || v.level !== "partial") return false;
  const coverage = finite(v.coverage);
  return coverage != null && coverage <= FRAMING_MAX_COVERAGE;
}

/** The canvas a readiness goal is really pricing, or `null` to leave the
 * verdict exactly as it is.
 *
 * "goal ~2 h · 1 min of ~2 h — a good start" is true of the single field it
 * measures, and it sat an inch under "Shooting it in mosaic mode next session
 * is the biggest win here" and "…is about 18 h of shooting". Nobody is being
 * told to point two ways — but a beginner asking *how much more do I need?*
 * got **~2 h** from the card whose whole job is answering that, about a canvas
 * the same screen had just recommended replacing.
 *
 * So the number stays (it is not wrong, and the mosaic is a genuinely different
 * target — the Seestar writes its subs to `<T>_mosaic_sub/`, so a card that
 * silently switched to 18 h would price a canvas the owner does not have and
 * break its own "of your total exposure" arithmetic). What it gains is the
 * scope it always assumed: *"1 min of ~2 h **for this single field** — a good
 * start"*. One clause, on the card that already exists, and only where the page
 * has **measured** a fragment — not on every oversized object, which would put
 * a new clause on a card a big-object owner sees constantly.
 */
export function readinessCanvasScope(
  v: NextBestMoveFraming | null | undefined,
): string | null {
  if (!framingIsFragment(v)) return null;
  return v?.canvas === "mosaic" ? "this mosaic" : "this single field";
}

/** Coaching kinds that prescribe **more light on the canvas the picture already
 * has** — the levers the framing note's "adding more panels next session would
 * capture the rest" competes with for one night.
 *
 * `thin`, `integration` and `good` all end on "shoot this again"; `locate` and
 * `soft` name a setup fix instead, and `framing` *is* the widen prescription, so
 * none of those three is a lever the clause below could defer to without
 * becoming a third opinion. */
const DEPTH_FIRST_COACH_KINDS: ReadonlySet<NextBestMoveKind> =
  new Set(["thin", "integration", "good"]);

/** The clause that puts the framing note's widen-prescription in its place, or
 * `null` to leave that note exactly as it is.
 *
 * This is the other side of `framingRung`. Below `FRAMING_MAX_COVERAGE` the
 * coaching card *becomes* the framing advice and the two agree. **Above** it,
 * the coaching card has deliberately decided the opposite — that depth beats
 * width on this picture — and nothing carried that decision to the note an inch
 * below, which goes on saying "Adding more panels next session would capture the
 * rest". Photographed on the bundled 2x2 at 75 % captured: one card asking for
 * another pass over the panels already shot, the other for more panels, on the
 * same screen, for the same night, with no word about which wins.
 *
 * So the note keeps its sentence — the missing quarter is real and the reader
 * should know about it — and gains the order. It is the mirror of
 * `IntegrationTrendBadge`'s own deference, and like it, it asks the coaching
 * card's *actual* verdict rather than re-deriving one: silent unless that card
 * is currently naming a more-light lever (`DEPTH_FIRST_COACH_KINDS`), so it can
 * never contradict a "refocus" or "install the star database" tip, and silent
 * on every surface that has no coaching card at all (the editor, History) —
 * which is what an omitted `coachKind` means.
 *
 * Requires a *measured* coverage above the bar, never merely "not a fragment":
 * a `partial` verdict whose coverage didn't come through says nothing about how
 * much is already in, and "most of it is already in this picture" would then be
 * a guess.
 */
export function framingDepthFirstClause(
  v: NextBestMoveFraming | null | undefined,
  coachKind: NextBestMoveKind | null | undefined,
): string | null {
  if (!v || v.level !== "partial") return null;
  const coverage = finite(v.coverage);
  if (coverage == null || coverage <= FRAMING_MAX_COVERAGE) return null;
  if (coachKind == null || !DEPTH_FIRST_COACH_KINDS.has(coachKind)) return null;
  const lever = v.canvas === "mosaic"
    ? "more passes over the panels you already have do more for it than a wider grid"
    : "more time on this framing does more for it than a wider canvas";
  return `Most of it is already in this picture, though — until you're happy ` +
    `with the depth, ${lever}.`;
}

/** The `framing` rung, or `null` when this run's framing isn't the top lever.
 *
 * Silent unless the verdict names a fragment (`framingIsFragment`) *and* the
 * backend served the friendly percentage the sentence names (an older one
 * didn't, and re-rounding it here is exactly the drift the shared number exists
 * to prevent). Either missing leaves the ladder byte-for-byte what it was.
 *
 * The sentence repeats the framing card's measurement rather than pointing at
 * it, which the standing IA rule would normally discourage — but `NoticeBoard`
 * shows two notes and folds the rest, and this card sorts *above* the framing
 * one, so on a busy target the reader can easily have this sentence inline and
 * that one folded. A coaching line that says "see the note you cannot see" is
 * worse than a repeated percentage.
 */
function framingRung(v: NextBestMoveFraming | null | undefined): NextBestMove | null {
  if (!v || !framingIsFragment(v)) return null;
  const pct = finite(v.coverage_pct);
  if (pct == null) return null;
  // The catalogue's friendly name when there is one; otherwise say it without,
  // never "undefined is bigger than your frame".
  const name = (v.object_name ?? "").trim();
  const it = name || "this target";
  if (v.canvas === "mosaic") {
    return {
      kind: "framing",
      phrase:
        `A large part of ${it} is still outside this mosaic — only about ` +
        `${pct}% of it made it in. Adding more panels next session is the ` +
        `biggest win here: more passes over the panels you already have can ` +
        `deepen this picture, but they can't bring the rest of it in.`,
    };
  }
  return {
    kind: "framing",
    phrase:
      `A large part of ${it} is still outside this picture — only about ` +
      `${pct}% of it made it in, and it's bigger than one frame, so more time ` +
      `can't bring the rest in. Shooting it in mosaic mode next session is the ` +
      `biggest win here; you can build up depth once the whole object is in ` +
      `the picture.`,
  };
}

/**
 * Pick the single highest-leverage next step for a finished stack, or `null`.
 *
 * Fixed priority ladder (only the top unmet lever ever fires):
 *   1. `locate`      — a real share of subs failed to plate-solve.
 *   2. `thin`        — barely any subs on any one part of the picture (also
 *                      covered by the louder thin-stack warning; kept here so
 *                      the ladder is complete).
 *   3. `soft`        — a healthy stack whose stars came out softer than usual for
 *                      this target (relative to its own history) → check focus.
 *   4. `framing`     — a healthy stack of only *part* of the object, because the
 *                      object is bigger than the canvas: capturing the rest
 *                      outranks deepening the fragment (see
 *                      `FRAMING_MAX_COVERAGE`). Below `soft` on purpose — a
 *                      refocus tightens the panels you are about to shoot too.
 *   5. `integration` — a healthy stack but under a quarter of this object
 *                      type's integration goal, *per pixel* (~1 h for a
 *                      nebula or an unrecognised target; see `integrationBars`).
 *   6. `good`        — decent result; encourage + name the one lever (time) that
 *                      still helps. Silent once the stack is genuinely deep. On
 *                      a mosaic the run's own `grain_verdict` says whether that
 *                      praise is true of the whole canvas or only of most of it,
 *                      and the phrase says which (see the rung).
 */
export function nextBestMove(input: NextBestMoveInput): NextBestMove | null {
  const nUsed = finite(input.nFramesUsed);
  // Nothing stacked yet → nothing to advise on.
  if (nUsed == null || nUsed < 0) return null;

  const nUnsolved = Math.max(0, finite(input.nUnsolved) ?? 0);
  const integrationS = finite(input.integrationS);
  // On a mosaic the two "how much have I got?" rungs below are asked of one
  // part of the picture, not of the target — see the constants above.
  const mosaic = spansMoreThanOneField(input.fieldFulls);
  const depth = mosaic ? Math.round(perPixel(nUsed, input.fieldFulls)) : nUsed;
  const perPixelS =
    integrationS == null ? null : perPixel(integrationS, input.fieldFulls);
  // "How much is enough here?" is the readiness card's question, so take its
  // answer rather than a second one — see `integrationBars` above.
  const bars = integrationBars(input.objectType, input.difficulty);

  // 1. Can't-locate-subs. The unsolved subs never reached the stacker, so
  //    getting them to plate-solve adds real frames — the biggest lever when a
  //    meaningful share of the session is stuck as "not located".
  const nStackable = nUsed + nUnsolved;
  if (
    nUnsolved >= LOCATE_MIN_UNSOLVED &&
    nStackable > 0 &&
    nUnsolved / nStackable >= LOCATE_MIN_FRACTION
  ) {
    return {
      kind: "locate",
      phrase:
        `Only ${nUsed} of your ${nStackable} subs were located and stacked — ` +
        `the other ${nUnsolved} couldn't be plate-solved, so they were left ` +
        `out. Installing ASTAP's star database (in Settings) usually lets far ` +
        `more of them stack, which is the biggest thing that would improve ` +
        `this picture.`,
      action: {
        label: "Check your star database in Settings \u2192",
        href: settingsLink("plate-solving"),
      },
    };
  }

  // 2. Too-thin. Barely any subs on any one part of the picture, so the noise
  //    never averages down there.
  if (depth <= THIN_STACK_MAX_FRAMES) {
    return {
      kind: "thin",
      phrase: mosaic
        ? `Your ${nUsed} subs are spread across ${fieldsOfSkyLabel(input.fieldFulls)}, ` +
          `so ${A_TYPICAL_PART} of this picture has only about ${depth} ` +
          `${depth === 1 ? "sub" : "subs"} on it — too few to smooth out the ` +
          `noise. More passes over the same mosaic is the biggest win here; ` +
          `a stack only gets cleaner as it combines more frames.`
        : `This stack combined only ${depth} ${depth === 1 ? "sub" : "subs"} — ` +
          `too few to smooth out the noise. Adding more subs is the biggest win ` +
          `here; a stack only gets cleaner as it combines more frames.`,
    };
  }

  // 3. Soft-stars. A healthy stack, but its stars came out softer than this
  //    target's own usual (a relative signal — no absolute px bar, so no
  //    per-camera calibration needed). A quick refocus next session is the
  //    highest-leverage fix — it tightens every future sub — so it outranks the
  //    add-time nudges below. Only ever fires on a real regression vs history.
  if (input.softStars) {
    const now = input.softStars.currentFwhmPx.toFixed(1);
    const usual = input.softStars.typicalFwhmPx.toFixed(1);
    return {
      kind: "soft",
      phrase:
        `Your stars came out a little softer than usual on this one — about ` +
        `${now} px across, vs your typical ${usual} px for this target. A quick ` +
        `refocus at the start of your next session usually tightens them back ` +
        `up, which sharpens every sub you shoot.`,
    };
  }

  // 4. Framing. The stack is healthy, but it is a stack of only *part* of the
  //    object — and the two "add more light" rungs below prescribe a different
  //    next session from the framing card on the same page. Ask that card's own
  //    measurement rather than a second opinion about it, so this can only ever
  //    fire when the sentence it is deferring to is genuinely on screen.
  //
  //    It sits above the time rungs because more time cannot buy what never
  //    lands on the sensor, and — on a single field — the depth it would buy is
  //    stranded: the Seestar writes mosaic subs into a separate `_mosaic_sub`
  //    folder, so switching to mosaic mode starts a *new* target and the hours
  //    added to the narrow field do not carry over. It sits below `soft`
  //    because a refocus tightens the wider session too.
  const framingMove = framingRung(input.framing);
  if (framingMove) return framingMove;

  // The integration-based levers need a known total exposure. Without it, a
  // healthy stack gets no guess — stay silent rather than invent advice.
  if (integrationS == null || perPixelS == null) return null;

  // 5. Short-integration. A healthy frame count but not much light where the
  //    beginner is looking; more hours is the lever that pulls out faint detail
  //    on deep-sky targets.
  if (perPixelS < bars.shortS) {
    const mins = Math.round(perPixelS / 60);
    const soFar = mins > 0 ? `${mins} min so far` : "only a few minutes so far";
    // A cluster is the one bucket where "galaxies and nebulae reward hours" is
    // simply not a fact about the thing on screen: `target_difficulty` calls
    // clusters "uniformly easy — bright point sources that need no integration
    // to look good", and their goal is the shortest the app has. Asking for
    // "another clear night or two" there contradicts the badge two inches up
    // the page saying it looks good in well under an hour, so say the true
    // thing and name the smaller lever it actually needs.
    //
    // …and a cluster is only *one* of the things that earn that badge. The words
    // quoted above are `target_difficulty`'s **easy** verdict, which every
    // curated-easy nebula and galaxy prints too — M42, M31, the Blue Snowball,
    // the Cat's Eye — and this branch never asked. Photographed on the bundled
    // M42 sample: the coaching card read "Galaxies and nebulae reward hours, so
    // another clear night or two on this target" with "It usually looks good in
    // well under an hour" in the object card below it, and the readiness card
    // between them quoting a goal of ~2 h — a night or two being several times
    // the whole goal.
    //
    // So ask the question once, from the two classifications that already
    // exist rather than from a new threshold: the type rule (clusters are
    // uniformly easy) and the curated verdict. `goalDifficultyFactor` is the
    // very function the goal these bars are fractions of is scaled by, so this
    // rung and that goal cannot come to different opinions about one object; it
    // returns 1 for an un-curated verdict, an unknown level, and an older
    // backend, all of which leave this phrase exactly as it was.
    const cluster = objectTypeBucket(input.objectType) === "Cluster";
    const curatedEasy = goalDifficultyFactor(input.difficulty) < 1;
    // Spelled as one subject so the Cluster sentences stay byte-for-byte what
    // they have said since v0.429.2 — only the set of targets that get them
    // grows.
    const quickly = cluster
      ? "Clusters come up quickly"
      : "This one comes up quickly for a Seestar";
    // …and the easy/cluster half of that sentence promises a *cleaner
    // background*, which is the one claim this target's own measured grain can
    // already have disproved. `grainProjection`'s module docstring says so in
    // as many words — its clean verdict "deliberately says more time now buys
    // **faint detail** rather than a visibly cleaner background… it agrees with
    // the 'keep going to pull out fainter detail' sitting directly above it" —
    // and that reconciliation was written against the *other* branch, the one
    // that really does say faint detail. v0.429.2 and v0.435.5 then widened this
    // easy/cluster branch over the same rung without asking, so on a
    // curated-easy target measuring clean the two cards sat one inch apart
    // saying opposite things ("would clean up the background nicely" over "the
    // background already looks clean… more time from here mostly buys fainter
    // detail rather than a visibly cleaner picture").
    //
    // The lever does not change — under a quarter of the goal, more time is
    // still the right advice and still buys real faint detail — only the reason
    // given for it, and only when the picture has actually been measured clean.
    // Any other level, or no measurement at all, keeps every phrase below
    // byte-for-byte what it has said since v0.435.5.
    const alreadyClean = input.grainLevel === "clean";
    // Scoped the way v0.437.3/v0.437.4 scope the same family: σ is one estimate
    // over the whole canvas, so on an unevenly deep mosaic "already clean"
    // describes most of it and the thin part still only comes down with light.
    // Read from the same field the `good` rung reads, so the ladder holds one
    // notion of "is this canvas uneven" rather than two.
    const uneven = input.grainVerdict === "uneven";
    return {
      kind: "integration",
      phrase: mosaic
        ? `Add more time — your ${formatIntegration(integrationS)} is spread across ` +
          `${fieldsOfSkyLabel(input.fieldFulls)}, so ${A_TYPICAL_PART} of this ` +
          `picture ` +
          `has ${soFar}. ` +
          (cluster || curatedEasy
            ? (alreadyClean && uneven
              ? `${quickly}, and across most of it the background already looks ` +
                `clean — so another pass or two over the same mosaic evens out ` +
                `the thinner part, and elsewhere pulls out fainter detail.`
              : alreadyClean
                ? `${quickly}, and the background here already looks clean — so ` +
                  `more passes over the same mosaic now pull out fainter detail ` +
                  `rather than cleaning it up further.`
                : `${quickly}, so even another pass or two over the ` +
                  `same mosaic would clean up the background.`)
            : `Galaxies and nebulae reward hours, so more passes over ` +
              `the same mosaic would pull out much more faint detail.`)
        : `Add more time — ${soFar}. ` +
          (cluster || curatedEasy
            ? (alreadyClean
              ? `${quickly}, and the background here already looks clean — so ` +
                `more time now pulls out fainter detail rather than cleaning ` +
                `it up further.`
              : `${quickly}, so even the rest of one clear night on ` +
                `this target would clean up the background nicely.`)
            : `Galaxies and nebulae reward hours, so another clear night or two ` +
              `on this target would pull out much more faint detail.`),
    };
  }

  // Genuinely deep and healthy → nothing worth nudging; stay silent.
  if (perPixelS >= bars.deepS) return null;

  // 6. All good (decent depth, but more time always still helps).
  //
  // …except that "plenty of subs went in" is a claim about the *canvas*, and on
  // a mosaic whose panels are unevenly deep the canvas is not one number. Every
  // figure this rung reached here on is a mean over the whole raster
  // (`perPixel` is explicit that it is), so a raster that is comfortably deep on
  // average can hold a panel that is not — and the "How's my stack?" panel a
  // little further down the same page says exactly that, with the depths it
  // measured off the coverage map: *"about 23 % of the picture has 3 subs on it
  // where most of it has 6, so that part looks about 1.4× grainier. That isn't
  // something processing can fix — grain only comes down with more light."*
  // "Plenty of subs went in" directly above that is the same substitution
  // v0.437.3 closed for the grain projection, and this is the other card that
  // makes it: both are true of the region each measured, and a beginner cannot
  // hold them at once.
  //
  // So the praise keeps its scope and the lever names *where*. `grain_verdict`
  // is the health note's own verdict, read off the same run, so the two cannot
  // come to different opinions about one picture — and it is null on a single
  // field and on an even mosaic, which is why nothing else here has to change.
  // The prescription matches both endings that note can print ("another night
  // on that panel", and "it evens out on its own as you keep shooting"): more
  // passes over the same mosaic is what serves either.
  if (input.grainVerdict === "uneven") {
    return {
      kind: "good",
      phrase:
        `Across most of it this is a solid result — plenty of subs went in. ` +
        `One part of this mosaic is thinner than the rest, though, and only ` +
        `more light evens that part out, so more passes over the same mosaic ` +
        `are what'll add depth from here.`,
    };
  }
  return {
    kind: "good",
    phrase:
      `This is a solid result — plenty of subs went in. More time is the main ` +
      `thing that'll add depth from here, so keep revisiting it on clear nights.`,
  };
}
