/** Keeping the cached frame list right after a single-frame grade, without
 * re-downloading every sub of the target.
 *
 * Grading a frame — the `a`/`r` keys, or the accept toggle on a row — used to
 * end in `invalidateQueries(["frames", safe])`, which refetches the **whole**
 * list. That list is deliberately complete: `api.listFrames` pages until it
 * holds every sub, because a fixed cap hid the newest frames from the table,
 * the keyboard grading and the Stack pre-flight guards. Measured on the running
 * app, a frame row is **531 bytes** on the wire (and that is a floor — the
 * sample's filenames are shorter than a Seestar's), so one keystroke cost:
 *
 * | subs   | re-downloaded per grade | requests |
 * |--------|-------------------------|----------|
 * |    200 |                  106 KB |        1 |
 * |  5,477 |                  2.9 MB |        3 |
 * | 35,894 |                 19.1 MB |       18 |
 *
 * 5,477 and 35,894 are the owner's two deepest targets, the requests are
 * **sequential** (each page waits for the last), and grading is the one thing
 * on this page you do dozens of times in a row. Over a NAS, from a phone, that
 * is the keyboard shortcut being unusable at exactly the depth that makes
 * grading worth doing.
 *
 * It is also avoidable, exactly rather than approximately. `PATCH
 * /api/targets/{safe}/frames/{id}` writes **one** row (`accept`,
 * `reject_reason`, `user_override`, or `bayer_pattern`) and returns that row in
 * full, so the fresh list a refetch would produce differs from the cached one in
 * precisely that row. Swapping it in is the same answer for no bytes.
 *
 * Two properties make the swap safe to do in place rather than re-sorting:
 * the table's sort keys are `id`, `timestamp_utc` and the five QC metrics
 * (`FRAME_COLUMNS`), and **none of them is a field `FramePatch` can change** —
 * so a graded row cannot move. And the replacement is identity-stable: a list
 * that does not hold the id comes back as the *same array*, so a cache entry
 * for another target is not invented or re-rendered.
 *
 * A *bulk* action is deliberately left invalidating. It changes many rows and
 * server-computed reject reasons (`bulk:worst:fwhm_px`), returns ids rather
 * than rows, and is a deliberate click rather than a keystroke — so there is
 * nothing exact to swap in and nothing to gain by guessing.
 */
import type { Frame } from "../../api/client";

/** `list` with the row whose id matches `updated` replaced by it.
 *
 * Returns `list` itself — the same reference — when no row has that id, so a
 * cache entry the update does not concern is left untouched rather than
 * replaced by an equal copy.
 */
export function replaceFrameInList(list: Frame[], updated: Frame): Frame[] {
  const at = list.findIndex((f) => f.id === updated.id);
  if (at < 0) return list;
  const next = list.slice();
  next[at] = updated;
  return next;
}
