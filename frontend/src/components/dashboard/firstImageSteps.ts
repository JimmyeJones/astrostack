import type { DashboardStats, SystemInfo } from "../../api/client";
import { settingsLink } from "../../settingsSections";

/**
 * "Your first image" — the ordered map of the journey a brand-new user has to
 * walk, and which parts of it they've already done.
 *
 * The first time someone opens AstroStack they face a wall of screens (Dashboard,
 * Library, Calibration, Stack, Editor, History, Storage) with no idea which one
 * comes first. The only first-run help today is the two *setup-problem* banners
 * (`astapReadiness`, `folderReadiness`) — they fire only when something is
 * misconfigured, so a beginner whose ASTAP and folders are fine gets no guidance
 * at all. This is the positive version: six plain steps, in order, each ticking
 * itself off from state the app already reports.
 *
 * The last two — finish it in the editor, then save that version — are the half
 * of the journey the card used to only *mention* in its congratulation, because
 * nothing cheap reported them. `/api/stats` now carries `n_edited_runs` /
 * `n_finished_pictures` (counted on the library roll-up it already does), so a
 * beginner who has just made their first stack is told what to do with it
 * instead of being congratulated and left on a linear, unstretched picture.
 *
 * Every signal comes from `GET /api/system` and `GET /api/stats`, which the
 * Dashboard already fetches — no new endpoint, no new engine math, nothing
 * written anywhere. Pure so the wording and the tick logic are unit-tested.
 */
export interface FirstImageStep {
  /** Stable id (used as a React key and in tests). */
  key: string;
  /** The step itself, as one plain imperative sentence. */
  label: string;
  /** One sentence of why/how, jargon-free. */
  hint: string;
  /** The page that does this step. */
  href: string;
  /** Link text for `href`. */
  action: string;
  done: boolean;
  /**
   * The keys whose completion *proves* this step was passed, whether or not it
   * ticked itself.
   *
   * The ticks are not monotonic, because `solve` measures **setup** (is ASTAP
   * installed?) while the rest measure **outcomes** (do you have frames, a
   * stack, an edit?). The bundled sample ships pre-solved, so someone who
   * presses "Stack it" on it finishes the whole journey with the setup step
   * still open — and a "what next?" that just took the first unticked step then
   * told them to go back and do step two (photographed 2026-09-12).
   *
   * Position alone can't decide this: `checked` is done by QC, which needs no
   * plate solve at all, so a *real* first-timer with no ASTAP sits at
   * `[frames ✓, solve ✗, checked ✓, …]` and solving genuinely is their next
   * step. Only `stack` and what follows it prove the solve happened. Hence a
   * named list per step rather than "anything later".
   */
  passedWhen?: string[];
}

/**
 * The steps that make the *first picture* — everything up to and including the
 * stack. They are the ones that decide whether this install has ever been
 * mid-journey (see {@link firstImageHasPicture}), which is what keeps the card
 * off a box that already had pictures before the card existed.
 */
export const FIRST_PICTURE_STEP_KEYS = ["frames", "solve", "checked", "stack"];

/**
 * The six steps and their live tick state, in the order a beginner does them.
 *
 * `system`/`stats` may be undefined while the Dashboard's queries are in flight;
 * an absent signal reads as **not done**, so the card never claims progress it
 * can't see (and never flickers a tick off once the data lands).
 */
export function firstImageSteps(
  system: SystemInfo | undefined,
  stats: DashboardStats | undefined,
): FirstImageStep[] {
  const astap = system?.astap;
  // The star database is optional on some ASTAP builds, so only a *false*
  // `star_db_found` counts against it — same one-sided rule the readiness
  // banner uses, so the two can never disagree about whether solving is ready.
  const solveReady = !!astap?.found && astap?.star_db_found !== false;
  return [
    {
      key: "frames",
      label: "Point AstroStack at your subs",
      hint: "Drop your Seestar folders into the watched folder on your NAS, or "
        + "upload FITS files straight from the Library page.",
      href: "/library",
      action: "Open Library",
      done: (stats?.n_frames ?? 0) > 0,
      // Grading, stacking or editing anything at all means the frames arrived.
      passedWhen: ["checked", "stack", "edit", "export"],
    },
    {
      key: "solve",
      // Says what the tick below actually measures. It used to read "Let it work
      // out where each frame points" — a claim about *your frames* — while the
      // tick reads whether ASTAP is installed. Those come apart on the app's own
      // first-run path: the bundled sample ships pre-solved, so someone who
      // presses "Stack it" gets a finished picture and a card reading "3 of 4
      // done" with *this* step, the one before it, unticked. The hint and the
      // tick always agreed it was a setup step; only the label didn't.
      label: "Set up plate solving (ASTAP)",
      hint: "Plate solving (ASTAP) is how AstroStack recognises the patch of sky "
        + "in each sub, so it can line them all up. Set it up once and forget it.",
      href: settingsLink("plate-solving"),
      action: "Check the setup",
      done: solveReady,
      // `stack` and no earlier: `run_stack` combines only *solved* frames, so a
      // stack run proves solving happened — while `checked` proves nothing,
      // because QC measures and grades a sub without any plate solution.
      passedWhen: ["stack", "edit", "export"],
    },
    {
      key: "checked",
      label: "Let it check and grade your frames",
      hint: "AstroStack measures every sub and sets the blurry ones aside on its "
        + "own — you don't have to click through thousands of them.",
      href: "/library",
      action: "Pick a target",
      done: (stats?.n_frames_accepted ?? 0) > 0,
      // A stack is built from accepted frames, so one existing means grading ran.
      passedWhen: ["stack", "edit", "export"],
    },
    {
      key: "stack",
      label: "Stack them into your first picture",
      hint: "Open a target and press \"Process this target\" — it checks, locates "
        + "and stacks in one go, then finishes the picture for you.",
      href: "/library",
      action: "Pick a target",
      done: (stats?.n_stack_runs ?? 0) > 0,
      // An edit or a finished picture is an edit *of a stack*.
      passedWhen: ["edit", "export"],
    },
    {
      key: "edit",
      // Ticks on a *saved recipe*, which an unattended auto-edit writes too — so
      // the label is about the picture being finished, never about who pressed
      // the button. Someone whose walk-away run auto-edited itself has genuinely
      // had this step done for them, and being told to go and do it again would
      // be the same "the tick and the label disagree" bug the solve step above
      // was fixed for.
      label: "Finish it in the editor",
      hint: "A fresh stack is flat and dark on purpose. Open it in the editor "
        + "and press Auto — it stretches, colour-balances and cleans it up in "
        + "one click, and nothing you do there touches the original.",
      href: "/gallery",
      action: "Open a picture",
      // A finished picture counts here too, and not only for tidiness: pressing
      // Export without ever pressing Save leaves the export marker and no saved
      // recipe, and this step reading the recipe alone would then sit unticked
      // *above* a ticked "Save your edited version". A later step being done is
      // proof this one was.
      done: (stats?.n_edited_runs ?? 0) > 0 || (stats?.n_finished_pictures ?? 0) > 0,
    },
    {
      key: "export",
      // Ticks on the *visible* picture being the finished one, which an in-place
      // "Process target" Auto edit already achieves without any export — so a
      // walk-away owner is never told to go and finish something the app
      // finished for them. The hint below only ever leads when the step is
      // genuinely open, and there its claim about the thumbnail is exactly true.
      label: "Save your edited version",
      hint: "Press Export in the editor to save your edit as its own picture — "
        + "until you do, the thumbnail everyone sees is still the un-edited "
        + "stack. Then it's in your Gallery to download or share.",
      href: "/gallery",
      // Distinct from the step above even though both land on the Gallery: while
      // both are open the card shows both links, and two identically-named ones
      // tell the user nothing about which is which.
      action: "Open your edit",
      done: (stats?.n_finished_pictures ?? 0) > 0,
    },
  ];
}

/**
 * True when this install has made a first picture *by any route* — every
 * first-picture step ticked, or a stacked Moon/Sun still.
 *
 * Deliberately blind to the two editor steps, because this is the predicate the
 * card uses to decide whether an install was ever seen mid-journey. Reading the
 * finishing steps here would make an established box — hundreds of stacks, none
 * of them exported — look like a beginner who has just started, and the card
 * would appear on a Dashboard it has never shown on. See `FirstImageCard`.
 */
export function firstImageHasPicture(
  steps: FirstImageStep[],
  stats: DashboardStats | undefined,
): boolean {
  const core = steps.filter((s) => FIRST_PICTURE_STEP_KEYS.includes(s.key));
  return (core.length > 0 && core.every((s) => s.done))
    || (stats?.n_video_stills ?? 0) > 0;
}

/** Every step ticked — the point the card turns into its one-line well-done. */
export function firstImageComplete(steps: FirstImageStep[]): boolean {
  return steps.length > 0 && steps.every((s) => s.done);
}

/**
 * True when the user has a finished picture *by any route* — including a
 * stacked Moon or Sun video.
 *
 * Every signal the steps read is deep-sky (frames ingested, frames solved,
 * stack runs, edits saved), and a video capture does none of those by design: it ingests no
 * FITS, solves nothing, and creates no `stack_runs` row. So someone whose first
 * picture is the Moon can never tick a single step, and the card would keep
 * telling them to go and make their first picture while it hangs in the Gallery.
 *
 * The **steps themselves are deliberately left alone** — they describe the
 * deep-sky journey and are still exactly the right advice for what to do next.
 * Only the "you have a picture" *outcome* recognises a still, so the card
 * congratulates and retires instead of nagging.
 */
export function firstImageDone(
  steps: FirstImageStep[],
  stats: DashboardStats | undefined,
): boolean {
  return firstImageComplete(steps) || (stats?.n_video_stills ?? 0) > 0;
}

/**
 * The congratulation, worded for how they actually got there — pointing a
 * Moon-video user at the editor they can't use would be worse than saying
 * nothing.
 */
export function firstImageDoneMessage(steps: FirstImageStep[]): string {
  if (firstImageComplete(steps)) {
    return "That's the whole journey — shot, stacked, finished and saved. Your "
      + "picture is in the Gallery whenever you want to look at it or share it.";
  }
  return "You've made your first picture — your Moon/Sun still is in the "
    + "Gallery. Deep-sky targets take the steps below whenever "
    + "you're ready for one.";
}

/**
 * The step the user should do next — the first unticked step **they have not
 * already gone past** — or null when there is nothing ahead of them.
 *
 * "The first unticked step" is not the same thing, and the difference is
 * user-visible: the ticks are not monotonic. `solve` is a *setup* step (is ASTAP
 * installed?) while the four around it are *outcome* steps (do you have frames,
 * a stack, an edit?), so the bundled sample — which ships pre-solved — ticks
 * every outcome and leaves the setup open. The card then read "5 of 6 done" with
 * five struck-through lines and led with **"Next: Plate solving (ASTAP) is how
 * AstroStack recognises the patch of sky in each sub…"**, i.e. it told someone
 * holding a finished, saved picture that the next thing to do was step two.
 * (Photographed 2026-09-12 by dogfooding the sample, which is the app's own
 * first-run path — the Dashboard offers a "Stack it" button for it.)
 *
 * So "next" means *ahead*: the first unticked step that no completed step
 * proves they already walked past (`passedWhen`). A step they have demonstrably
 * overtaken is still shown in the list, still unticked and still carrying its
 * link — nothing is hidden, it just stops being announced as what to do next.
 * Null means "nothing ahead", which the card words for itself; the setup banner
 * that owns that fact (`astapReadiness`) says it on the same screen either way.
 */
export function firstImageNextStep(steps: FirstImageStep[]): FirstImageStep | null {
  const done = new Set(steps.filter((s) => s.done).map((s) => s.key));
  return steps.find((s) => !s.done && !_passed(s, done)) ?? null;
}

/** Whether a later step being done proves this one was walked past. */
function _passed(step: FirstImageStep, done: Set<string>): boolean {
  return (step.passedWhen ?? []).some((k) => done.has(k));
}

/**
 * The unticked steps the user has already overtaken — a later step is done.
 *
 * Not "next", but not nothing either: on the sample path ASTAP genuinely isn't
 * set up and their *own* subs will need it, so the card names them rather than
 * falling silent once {@link firstImageNextStep} returns null.
 */
export function firstImageSkippedSteps(steps: FirstImageStep[]): FirstImageStep[] {
  const done = new Set(steps.filter((s) => s.done).map((s) => s.key));
  return steps.filter((s) => !s.done && _passed(s, done));
}

/**
 * The card's one lead sentence: what to do next, or — when they have overtaken
 * everything that is left — what is still open and why it will matter.
 *
 * Kept here rather than in the card so the wording is unit-tested next to the
 * tick logic that chooses it.
 */
export function firstImageLeadText(steps: FirstImageStep[]): string {
  const next = firstImageNextStep(steps);
  if (next) return `Next: ${next.hint}`;
  const skipped = firstImageSkippedSteps(steps);
  if (skipped.length === 1) {
    // Says both halves: you really did get through it, *and* the open step is
    // not optional once you point the scope at your own sky. The sample is what
    // let them skip it, and the sample is the only thing that can be stacked
    // without it.
    return "You've been all the way through. One step below is still open, and "
      + `you'll need it for your own subs — ${skipped[0].hint}`;
  }
  if (skipped.length > 1) {
    return "You've been all the way through. The steps below that aren't ticked "
      + "are still open, and you'll need them for your own subs.";
  }
  return "Six steps from a folder of subs to a finished picture.";
}
