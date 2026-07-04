import type { Pt } from "./curveDrag";

/** True when the Curves op's current control points already equal a suggested
 * point list — same length, each ``[x, y]`` within a tiny epsilon — so the
 * "Auto curve" button can dim (read as already-applied, with a ✓) rather than
 * invite a no-op click. This mirrors how the per-param data-driven buttons dim
 * via {@link matchesSuggestion} and how "Auto levels" dims via `levelsAtIdentity`,
 * completing the "name-the-goal + dim-when-applied" family for the tonal defaults.
 *
 * The suggestion (`suggest_tone_curve`) rounds each coordinate to 3 decimals and
 * the button applies exactly those points, so a small epsilon (well under half
 * the rounding step) keeps the match exact in practice while tolerating float
 * round-tripping. A missing/malformed current list, or an empty/absent
 * suggestion, never matches — so the button stays active. */
export function curvePointsMatch(
  current: unknown,
  suggested: readonly Pt[] | null | undefined,
): boolean {
  if (!suggested || suggested.length === 0) return false;
  if (!Array.isArray(current) || current.length !== suggested.length) return false;
  const EPS = 5e-4;
  return suggested.every((s, i) => {
    const c = current[i];
    return (
      Array.isArray(c)
      && c.length >= 2
      && typeof c[0] === "number"
      && typeof c[1] === "number"
      && Math.abs(c[0] - s[0]) <= EPS
      && Math.abs(c[1] - s[1]) <= EPS
    );
  });
}
