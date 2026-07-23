/** Pure helpers for the "My best pictures" wall.
 *
 * Turns a ranked {@link BestPicture} into the small plain-language "why it's one
 * of your best" line a beginner reads under each picture, e.g. "3.4 h · 500
 * frames". Every clause is best-effort: a missing datum (an old run with no
 * recorded integration time) drops that clause rather than printing a blank, so
 * the line always reads cleanly. Kept pure so a Vitest pins every degraded shape
 * without a DOM. */

import type { BestPicture } from "../api/client";
import { formatIntegration } from "../format";

/** The "why it's good" caption clauses for one picture, most-meaningful first:
 *  - integration time ("3.4 h") when the run recorded it, and
 *  - frame count ("500 frames").
 * Returns an empty array only for a run carrying neither (very old data); the
 * caller then just shows the picture with no subtitle. */
export function bestPictureClauses(pic: BestPicture): string[] {
  const clauses: string[] = [];
  if (
    pic.total_exposure_s != null &&
    Number.isFinite(pic.total_exposure_s) &&
    pic.total_exposure_s > 0
  ) {
    clauses.push(formatIntegration(pic.total_exposure_s));
  }
  if (Number.isFinite(pic.n_frames_used) && pic.n_frames_used > 0) {
    const n = pic.n_frames_used;
    clauses.push(`${n} ${n === 1 ? "frame" : "frames"}`);
  }
  return clauses;
}

/** The single-line "why it's good" caption ("3.4 h · 500 frames"), or "" when
 * the run carries neither integration time nor a frame count. */
export function bestPictureReason(pic: BestPicture): string {
  return bestPictureClauses(pic).join(" · ");
}
