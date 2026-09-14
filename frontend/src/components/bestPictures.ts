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
import { perPixel, spansMoreThanOneField } from "./target/perPixel";

/** How the wall's ranking actually works, in the words a beginner reads.
 *
 * One key per metric `seestack.portfolio.PORTFOLIO_WEIGHTS` blends, mapped to
 * the phrase the hint uses for it. A TypeScript file cannot import a Python
 * dict, so the key set is mirrored by hand and guarded by
 * `tests/test_portfolio_hint_mirror.py` — a fifth metric added to the scorer
 * turns that test red until this sentence names it.
 *
 * **Why this needed a guard.** The hint used to read *"picked automatically by
 * total integration time, cleanliness, and frame count"*, and both halves of
 * that were wrong: it named three of the four metrics (`coverage` has been in
 * the blend and unmentioned), and it called the leading one a **total** when
 * the ranker deliberately reads integration, frames and coverage *per pixel* —
 * dividing each by the run's `field_fulls` — precisely so a mosaic is judged on
 * how deep it is rather than on the sum of its panels. On a 3x3 raster those
 * are an order of magnitude apart, and this one sentence is the only thing on
 * the page that explains the order the pictures are in.
 */
export const RANKING_METRIC_WORDS: Record<string, string> = {
  exposure: "integration time",
  frames: "frame count",
  noise: "how clean it came out",
  coverage: "how deeply the subs overlap",
};

/** The wall's one-sentence explanation of its own ordering.
 *
 * Built from {@link RANKING_METRIC_WORDS} rather than written out, so the list
 * of metrics and the sentence that names them cannot drift into two answers.
 *
 * It opens on the *detail* rather than on "your finest finished stacks, ranked
 * automatically", because the page's intro paragraph an inch above already says
 * exactly that ("deepest, cleanest first") — checked in a browser, where the two
 * read as a stutter. The intro is the summary; this is what is behind it. */
export function rankingHint(): string {
  const { exposure, noise, frames, coverage } = RANKING_METRIC_WORDS;
  return (
    `Ranked by ${exposure}, ${noise}, ${frames} and ${coverage} — each ` +
    "measured on one part of the picture rather than added up across it, so a " +
    "mosaic is judged on how deep it is and not on the size of its canvas."
  );
}

/** The "why it's good" caption clauses for one picture, most-meaningful first:
 *  - integration time ("3.4 h") when the run recorded it,
 *  - frame count ("500 frames"), and
 *  - on a canvas spanning more than one field of sky, what one patch of it
 *    actually got ("about 51 min on each patch of sky").
 *
 * Returns an empty array only for a run carrying neither of the first two (very
 * old data); the caller then just shows the picture with no subtitle.
 *
 * **Why the third clause exists.** The first two are the *target's* totals, and
 * a mosaic spreads its subs across the raster: "3.4 h · 500 frames" on a 3×3 is
 * about 23 min and 55 subs anywhere you look. Read as a reason this picture is
 * one of someone's best, that overstates it by the number of field-fulls the
 * canvas spans — which is exactly the substitution `perPixel` exists to undo on
 * the Target page, and which the wall's own ranking now scores per pixel too
 * (`seestack.portfolio`). Every fact the old caption carried survives; the
 * clause only says which number is which. A single field, and an older backend
 * that sends no `field_fulls`, keep today's wording byte for byte. */
export function bestPictureClauses(pic: BestPicture): string[] {
  const clauses: string[] = [];
  const hasExposure =
    pic.total_exposure_s != null &&
    Number.isFinite(pic.total_exposure_s) &&
    pic.total_exposure_s > 0;
  if (hasExposure) {
    clauses.push(formatIntegration(pic.total_exposure_s as number));
  }
  const hasFrames = Number.isFinite(pic.n_frames_used) && pic.n_frames_used > 0;
  if (hasFrames) {
    const n = pic.n_frames_used;
    clauses.push(`${n} ${n === 1 ? "frame" : "frames"}`);
  }
  if (clauses.length > 0 && spansMoreThanOneField(pic.field_fulls)) {
    // Time when the run recorded it — the app's leading currency, and the one
    // the wall weights highest — else the depth in subs, so a run with no
    // integration time still gets scoped rather than left as a bare total.
    clauses.push(
      hasExposure
        ? `about ${formatIntegration(perPixel(pic.total_exposure_s as number, pic.field_fulls))}`
          + " on each patch of sky"
        : `about ${Math.max(1, Math.round(perPixel(pic.n_frames_used, pic.field_fulls)))}`
          + " subs on each patch of sky",
    );
  }
  return clauses;
}

/** The single-line "why it's good" caption ("3.4 h · 500 frames"), or "" when
 * the run carries neither integration time nor a frame count. */
export function bestPictureReason(pic: BestPicture): string {
  return bestPictureClauses(pic).join(" · ");
}

/** True when this picture is on the wall because the user pinned it as its
 * target's cover, rather than purely on the automatic ranking. Tolerates an
 * older backend that never sends the field (nothing is pinned there). */
export function isPinnedPick(pic: BestPicture): boolean {
  return pic.pinned === true;
}

/** The plain-language "why is this one here?" tooltip for a pinned picture —
 * the wall's score line can't explain a favourite the ranking didn't choose, so
 * say it outright. Returns null for an ordinary auto-picked entry. */
export function pinnedNote(pic: BestPicture): string | null {
  if (!isPinnedPick(pic)) return null;
  return `You picked this as ${pic.target_name}'s cover, so it always has a place here — even if another stack scores higher. Unpin it from that target's History page.`;
}
