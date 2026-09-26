/**
 * The words that go under the matched-crop "did it get better?" picture.
 *
 * The picture is two native-resolution crops of the *same* patch of sky — the
 * previous stack on the left, the newest on the right — drawn under one shared
 * stretch (see `seestack/render/noisedelta.py`). Pure string-building, kept out
 * of the component so the honesty rules below are testable on their own.
 *
 * Three of those rules matter more than the phrasing:
 *
 * * **Say which side is which.** Two squares side by side are meaningless
 *   without it, and "before/after" is the one thing a viewer cannot infer.
 * * **Only claim a number when the backend offered one.** `noise_ratio` is
 *   `null` whenever the two crops had to be resized to a common scale, because a
 *   resize lowers the resampled side's per-pixel grain for reasons that have
 *   nothing to do with stacking. No number then — the picture still stands.
 * * **Say it plainly when it got *worse*.** A restack can land grainier (a hazy
 *   night added, a canvas widened) and a card that can only report good news is
 *   not a measurement, it is decoration.
 */

/** A ratio as `"1.4"` / `"2"` — one decimal, no trailing `.0`. */
function times(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return rounded === Math.round(rounded) ? String(Math.round(rounded))
    : rounded.toFixed(1);
}

/** Below/above these the grain is called the same; ~15 % is about where a
 *  side-by-side at this size stops being arguable. */
const FINER = 1.15;
const COARSER = 1 / FINER;

export type NoiseDeltaInfo = {
  available: boolean;
  patch_px?: number | null;
  pixel_exact?: boolean | null;
  noise_ratio?: number | null;
};

/**
 * "Left: last time (12 Nov). Right: now (18 Nov)." — which half is which, dated
 * the same way the card's own sentence dates them. A missing date drops its
 * parenthesis rather than printing a blank one.
 */
export function noiseDeltaSides(previousLabel?: string | null,
                                newestLabel?: string | null): string {
  const left = previousLabel ? `Left: last time (${previousLabel}).`
    : "Left: last time.";
  const right = newestLabel ? `Right: now (${newestLabel}).`
    : "Right: now.";
  return `${left} ${right}`;
}

/**
 * The measured half, or `""` when there is nothing honest to say — no ratio at
 * all, or one the backend withheld because the two crops were not sampled the
 * same way.
 */
export function noiseDeltaVerdict(info?: NoiseDeltaInfo | null): string {
  const ratio = info?.noise_ratio;
  if (typeof ratio !== "number" || !Number.isFinite(ratio) || ratio <= 0) return "";
  if (info?.pixel_exact === false) return "";
  if (ratio >= FINER) {
    return `The grain here is about ${times(ratio)}× finer than last time.`;
  }
  if (ratio <= COARSER) {
    return `The grain here is about ${times(1 / ratio)}× coarser than last time`
      + " — a hazier night or a wider canvas can do that, even with more frames.";
  }
  return "The grain here is about the same as last time.";
}

/** The fixed explanation of what the two squares are, so nobody reads a
 *  brightness difference into a picture that has none by construction. */
export const NOISE_DELTA_BLURB =
  "The same patch of sky from both, at full resolution and under one shared"
  + " stretch — so the only difference you can see is the grain and the faint"
  + " detail underneath it.";
