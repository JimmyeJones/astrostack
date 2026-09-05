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
 * `n_exported_runs` (counted on the library roll-up it already does), so a
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
    },
    {
      key: "checked",
      label: "Let it check and grade your frames",
      hint: "AstroStack measures every sub and sets the blurry ones aside on its "
        + "own — you don't have to click through thousands of them.",
      href: "/library",
      action: "Pick a target",
      done: (stats?.n_frames_accepted ?? 0) > 0,
    },
    {
      key: "stack",
      label: "Stack them into your first picture",
      hint: "Open a target and press \"Process this target\" — it checks, locates "
        + "and stacks in one go, then finishes the picture for you.",
      href: "/library",
      action: "Pick a target",
      done: (stats?.n_stack_runs ?? 0) > 0,
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
      done: (stats?.n_edited_runs ?? 0) > 0,
    },
    {
      key: "export",
      label: "Save your edited version",
      hint: "Press Export in the editor to save your edit as its own picture — "
        + "until you do, the thumbnail everyone sees is still the un-edited "
        + "stack. Then it's in your Gallery to download or share.",
      href: "/gallery",
      // Distinct from the step above even though both land on the Gallery: while
      // both are open the card shows both links, and two identically-named ones
      // tell the user nothing about which is which.
      action: "Open your edit",
      done: (stats?.n_exported_runs ?? 0) > 0,
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

/** The step the user should do next (the first unticked one), or null when the
 *  journey is complete — so the card can lead with one thing rather than four. */
export function firstImageNextStep(steps: FirstImageStep[]): FirstImageStep | null {
  return steps.find((s) => !s.done) ?? null;
}
