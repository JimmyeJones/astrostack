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
/** True iff `pts` is exactly the untouched identity default `[[0,0],[1,1]]` —
 * mirrors the engine's `_points_are_identity` (tone.py), which is the condition
 * under which the Curves op's `auto` contrast engages (a hand-edited curve is
 * never overridden). Defensive against a malformed/absent list. */
export function isIdentityCurve(pts: unknown): boolean {
  if (!Array.isArray(pts) || pts.length !== 2) return false;
  const [a, b] = pts as unknown[];
  if (!Array.isArray(a) || !Array.isArray(b)) return false;
  const near = (v: unknown, t: number) => typeof v === "number" && Math.abs(v - t) < 1e-6;
  return near(a[0], 0) && near(a[1], 0) && near(b[0], 1) && near(b[1], 1);
}

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
