import type { StackRun } from "./api/client";

/**
 * Which of a target's stacks *is* "your picture" right now.
 *
 * The rule is the backend's, not a second opinion: `gallery._representative_run`
 * and `targets.current_picture_path` both resolve **the pinned cover first**, and
 * fall back to the newest run that still has a preview on disk. The Library tile,
 * the Best wall, the montage and the "your newest stack is grainier" note all
 * follow it. The Target page did not — it took `runs[0]` — so pinning run 3 and
 * re-stacking to run 4 left the page a beginner opens showing a *different
 * picture* from the card they clicked to get there, while its own notes talked
 * about "the cover".
 *
 * `newer` is the newest picture when a pinned cover is being shown instead of it,
 * so the card can say so rather than leaving someone to wonder whether their
 * restack ran. It is `undefined` whenever the picture on screen already is the
 * newest one.
 *
 * The final fallback is `runs[0]` even with no preview anywhere: the page's
 * action row (Edit, Stack) works on a run that has yet to render one, and this
 * must not take that away.
 */
export function representativeRun(
  runs: StackRun[] | undefined,
  coverRunId?: number | null,
): { run: StackRun | undefined; pinned: boolean; newer: StackRun | undefined } {
  const list = runs ?? [];
  const cover = coverRunId == null
    ? undefined
    : list.find((r) => r.id === coverRunId && r.has_preview);
  const newest = list.find((r) => r.has_preview) ?? list[0];
  if (!cover) return { run: newest, pinned: false, newer: undefined };
  return {
    run: cover,
    pinned: true,
    newer: newest && newest.id !== cover.id ? newest : undefined,
  };
}
