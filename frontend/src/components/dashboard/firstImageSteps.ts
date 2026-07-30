import type { DashboardStats, SystemInfo } from "../../api/client";

/**
 * "Your first image" — the ordered map of the journey a brand-new user has to
 * walk, and which parts of it they've already done.
 *
 * The first time someone opens AstroStack they face a wall of screens (Dashboard,
 * Library, Calibration, Stack, Editor, History, Storage) with no idea which one
 * comes first. The only first-run help today is the two *setup-problem* banners
 * (`astapReadiness`, `folderReadiness`) — they fire only when something is
 * misconfigured, so a beginner whose ASTAP and folders are fine gets no guidance
 * at all. This is the positive version: four plain steps, in order, each ticking
 * itself off from state the app already reports.
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
 * The four steps and their live tick state, in the order a beginner does them.
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
      label: "Let it work out where each frame points",
      hint: "Plate solving (ASTAP) is how AstroStack recognises the patch of sky "
        + "in each sub, so it can line them all up. Set it up once and forget it.",
      href: "/settings",
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
  ];
}

/** Every step ticked — the point the card turns into its one-line well-done. */
export function firstImageComplete(steps: FirstImageStep[]): boolean {
  return steps.length > 0 && steps.every((s) => s.done);
}

/** The step the user should do next (the first unticked one), or null when the
 *  journey is complete — so the card can lead with one thing rather than four. */
export function firstImageNextStep(steps: FirstImageStep[]): FirstImageStep | null {
  return steps.find((s) => !s.done) ?? null;
}
