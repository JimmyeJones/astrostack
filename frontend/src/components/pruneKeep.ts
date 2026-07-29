/** Pure guard for the Storage "Prune stacks" control.
 *
 * The prune box means "keep the N newest stacks and permanently delete the rest".
 * A Mantine `NumberInput` can be *emptied*, and `Number("") === 0`, so an
 * accidentally-cleared box used to sail through as `keep: 0` — which the backend
 * accepts (0 is a legitimate value for the explicit-ids delete path) and which
 * therefore **deleted every stack run for the target** behind a confirm that read
 * "Keep the 0 newest…". Keeping zero via this convenience control is never what a
 * beginner means, so we require at least one and reject anything else.
 *
 * @returns a safe integer keep-count (>= 1, clamped to the run count), or `null`
 *   when the input is empty/blank/non-positive/non-integer — the caller must then
 *   refuse to prune and prompt for a real number instead of silently deleting all.
 */
export function sanitizeKeep(
  value: number | string,
  maxRuns: number,
): number | null {
  const n = typeof value === "number" ? value : Number(String(value).trim());
  // Number("") === 0 and Number("  ") === 0 — the emptied-box footgun — so an
  // explicit blank check is needed before the numeric test below.
  if (typeof value === "string" && value.trim() === "") return null;
  if (!Number.isInteger(n) || n < 1) return null;
  return maxRuns > 0 ? Math.min(n, maxRuns) : n;
}
