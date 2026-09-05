import type { StackRun } from "./api/client";

/**
 * The bookmarkable `/compare` URL for two runs of the **same** target. The
 * Compare view resolves each `"<safe>:<run_id>"` ref against the gallery (which
 * carries every run), so a same-target link needs no backend change.
 *
 * One spelling, shared by History's per-row **Compare** button and the Target
 * page's "Compare with my last one" — two surfaces asking one question should
 * not be able to build two different links to the same page.
 */
export function sameTargetCompareHref(safe: string, aId: number, bId: number): string {
  return `/compare?a=${safe}:${aId}&b=${safe}:${bId}`;
}

/**
 * "Is my new picture actually better than last week's?" — which two runs the
 * Target page's one-click compare should open.
 *
 * The A/B route (`/compare?a=…&b=…`), its drag-the-divider split slider and its
 * plain-language noise / panel / nights verdicts have all existed since v0.150-
 * ish, and History offers the pairing per row — but a beginner who never opens
 * History never discovers any of it. This is the pure half of the one affordance
 * that closes that gap; the component around it is deliberately nothing more
 * than a link.
 *
 * Two rules, both about honesty rather than convenience:
 *
 * * **Both sides must have a picture.** A preview-less run (a channel-combine,
 *   or one whose preview file has gone) has nothing to put beside anything, and
 *   the Compare page would show it an empty panel.
 * * **Both sides must be genuine stacks.** An editor export (`reusable ===
 *   false`) is the *same* stack with a recipe baked on, so pairing it with the
 *   stack it came from answers "did my edit change anything?", not "did another
 *   two nights help?" — and the editor's own before/after already answers the
 *   first. `undefined` counts as genuine: an older backend that never sent the
 *   field has only ever had real stacks in this list.
 *
 * `null` — fewer than two qualifying runs — is the common case on a target that
 * has been stacked once, and the caller renders nothing at all rather than a
 * disabled control.
 */
export function pickCompareWithLast(
  runs: StackRun[] | undefined | null,
): { newest: StackRun; previous: StackRun } | null {
  // `listStackRuns` is newest-first, so the first two survivors are the pair.
  const usable = (runs ?? []).filter((r) => r.has_preview && r.reusable !== false);
  if (usable.length < 2) return null;
  return { newest: usable[0], previous: usable[1] };
}
