/**
 * Which of a target's runs is "the latest stack" the Target page's analysis
 * notes describe — the thin-stack warning, the noise badge, "sharpest yet",
 * the coaching line, the framing verdict.
 *
 * `listStackRuns` is newest-first by the date each picture was *stacked*. A
 * Combine carries the folded-in folder's pictures across with their own dates
 * (`carried_in`), and the folder being folded in is usually the most recent
 * night — so by date alone a one-night picture of 3 subs became "the latest
 * stack" of a deep target whose own picture has 4, and the page warned "Very
 * few frames were combined" beside the deep picture the Combine had pinned.
 *
 * So the latest stack is the newest run **made for this target**: the first
 * run not carried in. When every run was carried in (the target had no picture
 * of its own before the Combine) the newest run is still the answer, and a
 * backend too old to send the flag reads every run as its own — exactly the
 * old behaviour.
 *
 * Returns the list with that run moved to the front and the rest in their
 * original order, because the readers take `runs[0]` as "the current result"
 * and `runs.slice(1)` as its priors — a carried picture is still a prior
 * picture of the same object. Non-mutating.
 */
export function latestStackFirst<R extends { carried_in?: boolean }>(
  runs: R[] | null | undefined,
): R[] | undefined {
  if (!runs) return undefined;
  const i = runs.findIndex((r) => r.carried_in !== true);
  if (i <= 0) return runs;
  return [runs[i], ...runs.slice(0, i), ...runs.slice(i + 1)];
}
