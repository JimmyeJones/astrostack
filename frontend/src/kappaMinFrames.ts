/** How many subs must land on **one pixel** before κ-σ can drop a *lone*
 * satellite, plane or cosmic-ray hit.
 *
 * The frontend has been quoting this number in prose comments for months
 * ("11 at the default κ=3" appears in `rejectionReachNudge.ts`, `routes/Stack.tsx`,
 * `routes/Target.tsx` and `routes/History.tsx`) without ever being able to
 * *compute* it, so every surface that wanted to say it out loud either got the
 * figure from the backend or hard-coded the default-κ answer. This is the hand
 * mirror of `seestack.stack.stacker.kappa_min_frames`, so a chip that knows the
 * run's own κ can name the run's own bound.
 *
 * **Why the bound exists** (the engine's docstring, in one line): a single
 * point's z-score against statistics that still include it is at most
 * `(n−1)/√n`, which first reaches κ at `n = ⌈((κ+√(κ²+4))/2)²⌉`. Below that the
 * clip is *mathematically* blind to a lone outlier — it runs, records its mode,
 * and removes nothing. Floored at 3, the fewest samples any rejection can act
 * on (`MIN_MAX_MIN_FRAMES`, mirrored in `components/target/rejectionNote.ts`).
 *
 * The drizzle path shares this bound rather than having one of its own: its
 * two-pass clip is the same κ·σ test with the same κ, measured on a real drizzle
 * stack in `tests/test_drizzle_reject.py` (one sub's bright block is fully
 * diluted at every depth up to 10 and removed from 11, at κ=3). That is
 * `lone_outlier_min_depth`'s doing, and it is why this module is about the
 * *bound* rather than about one method.
 *
 * Mirrored by hand because a TS module cannot import a Python function — the
 * `formatRejectPct` arrangement — and pinned against it by
 * `tests/test_kappa_min_frames_mirror.py` through the shared case table
 * `kappaMinFrames.cases.json`, driven from both sides. Change the rule and you
 * have to change the table.
 */

/** The floor every rejection method shares: below three samples on a pixel there
 * is nothing to spare, whatever the method. Mirrors
 * `seestack.stack.stacker.MIN_MAX_MIN_FRAMES` (and the equal
 * `MIN_MAX_MIN_SAMPLES` in `components/target/rejectionNote.ts`, which is where
 * the min/max surfaces read it from — this copy exists so the formula below can
 * state its own floor without importing a note helper). */
const ABSOLUTE_MIN_FRAMES = 3;

export function kappaMinFrames(kappa: number | null | undefined): number | null {
  // A run with no readable κ gets no number rather than the default's: quoting
  // "about 11" for a stack clipped at κ=1.5 would be its own untruth, and the
  // callers all have a wording that works without the figure.
  if (kappa == null || !Number.isFinite(kappa) || kappa <= 0) return null;
  const u = (kappa + Math.sqrt(kappa * kappa + 4)) / 2;
  return Math.max(ABSOLUTE_MIN_FRAMES, Math.ceil(u * u));
}
