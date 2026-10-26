/** Honest "thin stack" warning — a stack whose picture is only a few subs deep.
 *
 * A stack only smooths noise as it combines more subs: measured on synthetic
 * faint-star fields the background noise falls ~√N (1→4 frames ≈ 2× cleaner,
 * 4→16 ≈ 2× again). So a "stack" of 1 frame is just one raw sub — it comes out
 * as per-pixel colour speckle ("gibberish"), exactly what a beginner sees when a
 * faint/sparse-star field loses most of its subs to plate-solve failure or
 * over-aggressive auto-reject. Rather than present that noisy result as a
 * finished picture with no explanation, surface a plain-language heads-up with a
 * concrete next step. Pure + threshold-driven so it's trivially unit-tested.
 *
 * **The threshold is a depth, not a count** (corrected 2026-09-11). "√N has
 * barely started averaging the sky down" is a claim about one pixel, and on a
 * mosaic the run's frame count is not that: nine subs over a 3×3 raster is one
 * sub everywhere, and it rendered as exactly the speckle this warning exists for
 * while the warning stayed silent because 9 > 4. That is the same substitution
 * `auto_stack_min_frames` was fixed for in v0.415.0 — which now *holds such a
 * mosaic back* rather than publishing it, so the two surfaces disagreed about
 * one picture. The depth comes from the run's own `field_fulls` (see
 * `perPixel.ts`); a single field is unchanged in every respect, wording
 * included.
 *
 * **`readyToStack` is what stops it guessing at the remedy** (added 2026-10-13,
 * found by `scripts/agent-dogfood.sh --combine`). The depth claim is a fact
 * about the picture and is right either way, but the *next step* was always
 * "check that your subs plate-solved and weren't over-rejected … then add more
 * subs" — and on the Target page a sibling note had already measured that N
 * subs were accepted, located and simply absent from this stack, which is the
 * one state where both halves of that advice are wrong: those subs did solve
 * and were not rejected, and he need not shoot anything. That mattered more
 * than "two notes disagree", because `NoticeBoard` keeps two notes inline by
 * priority: this warning is a `warning` and the corrective
 * "N subs missing from your current picture · Restack" is an `advisory`, so the
 * guess won the inline slot and the measured remedy sat behind "more notes".
 * The page passes the figure only when the picture on show *is* the run this
 * warning describes — see `Target.tsx` — because the two are otherwise measured
 * against different stacks. It is the same reconciliation the coaching line
 * already gets from `grainLevel` and `framing`.
 *
 * **`remedy` names the button that is actually on screen** (added 2026-10-26,
 * found by `--combine`'s step 9). While any accepted sub is still unlocated the
 * page swaps its "N subs missing · Restack" card for "Ready to process?", and it
 * used to drop the figure along with the card — so one new, unsolved sub dropped
 * in beside three located ones put "check your solves, then add more subs" back
 * over a target with three subs a click away. The figure is just as true then;
 * only the verb changes, to the "Process target" button that locates the new
 * subs and stacks the lot (the same chain the Restack button runs).
 *
 * Returns `null` for a healthy depth (no nag), otherwise a level + message.
 * `level` lets the UI pick colour/urgency: "single" (one sub deep — not really a
 * stack) vs "thin" (2–4 — very few).
 */

import {
  A_TYPICAL_PART,
  fieldsOfSkyLabel,
  perPixel,
  spansMoreThanOneField,
} from "./perPixel";

// At/under this many subs *on one part of the picture* the result is genuinely
// noisy and worth a heads-up. Chosen from the √N noise curve: below ~5 frames
// the stack has barely started averaging the sky down.
export const THIN_STACK_MAX_FRAMES = 4;

/** The Library wall's chip label for this state. One string, so the wall and any
 * future surface read identically — the message itself is `thinStackWarning`'s,
 * which is why there is no second sentence here. */
export const THIN_PICTURE_LABEL = "Thin — keep shooting";

/** Where the reader can see *why* subs were dropped, which is the first thing to
 * check before shooting more.
 *
 * `"this-page"` — the default, and every surface this warning had before the
 * Library wall got it — names the "rejected" count sitting above the badge on
 * the Target, Gallery and Jobs pages. A wall card has no such count on it, and
 * "see the count above" pointing at nothing is worse than a longer sentence, so
 * `"open-it"` sends the reader one click in, to the target page that does.
 */
export type ThinStackRejectedCountIs = "this-page" | "open-it";

export interface ThinStackWarning {
  level: "single" | "thin";
  /** Subs on one part of the picture — the run's frame count on a single field,
   *  and its per-pixel depth on a mosaic. The number the message is about. */
  frames: number;
  message: string;
}

export function thinStackWarning(
  nFramesUsed: number | null | undefined,
  /** How many single-frame field-fulls of sky the run's canvas covers
   * (`StackRun.field_fulls`). Omit / null / ≤1 on a single field and on any
   * surface that doesn't have the figure — the warning is then exactly what it
   * has always been. */
  fieldFulls?: number | null,
  /** Where the reader can find the "rejected" count — see
   * `ThinStackRejectedCountIs`. Defaults to the surfaces this warning was
   * written for, so every existing caller is unchanged word for word. */
  rejectedCountIs: ThinStackRejectedCountIs = "this-page",
  /** How many subs are accepted, located and **absent from this very stack** —
   * i.e. how many a restack would fold in without another night's shooting.
   * Omit / null / 0 on every surface that does not have the figure, and the
   * advice is exactly what it has always been. See `readyToStack` in the
   * module docstring for why it changes the sentence. */
  readyToStack?: number | null,
  /** Which button folds those subs in on this page right now — see `remedy` in
   * the module docstring. Only read when `readyToStack` is used. */
  remedy: "restack" | "process" = "restack",
): ThinStackWarning | null {
  // Unknown / not-yet-stacked → nothing to warn about.
  if (nFramesUsed == null || !Number.isFinite(nFramesUsed) || nFramesUsed < 0) {
    return null;
  }
  const mosaic = spansMoreThanOneField(fieldFulls);
  // Round the depth so the sentence and the test agree on one integer; a mean
  // depth of 4.6 is "about 5 subs", not a fifth of a sub short of the bar.
  const depth = mosaic
    ? Math.round(perPixel(nFramesUsed, fieldFulls))
    : nFramesUsed;
  if (depth > THIN_STACK_MAX_FRAMES) return null;

  const where =
    rejectedCountIs === "open-it"
      ? 'open it and check the "rejected" count'
      : 'see the "rejected" count above';
  // Subs already on disk that this stack does not contain. Floored and bounded
  // below, so a nonsense figure from a caller degrades to the old sentence
  // rather than into "0 more subs".
  const ready =
    readyToStack != null && Number.isFinite(readyToStack) && readyToStack >= 1
      ? Math.floor(readyToStack)
      : 0;
  const them = ready === 1 ? "it" : "them";
  const foldIn = remedy === "process"
    ? `press "Process target" to fold ${them} in (it locates your newest subs first)`
    : `restack to fold ${them} in`;
  const next = ready
    ? `You already have ${ready} more ${ready === 1 ? "sub" : "subs"} accepted and ` +
      `located that this stack didn't use — ${foldIn}, and a stack only gets ` +
      "cleaner as it combines more frames. No new shooting needed."
    : `Check that your subs plate-solved and weren't over-rejected (${where}), ` +
      "then add more subs — a stack only gets cleaner as it combines more frames.";

  if (mosaic) {
    // Name both figures. A mosaic owner reading "only 3 subs" under a picture
    // the same page says took 27 has been told two things that can't both be
    // true; the spread is the fact that reconciles them.
    const spread =
      `Your ${nFramesUsed} subs are spread across ${fieldsOfSkyLabel(fieldFulls)}, ` +
      `so ${A_TYPICAL_PART} of this picture has only about ${depth} ` +
      `${depth === 1 ? "sub" : "subs"} on it`;
    if (depth <= 1) {
      return {
        level: "single",
        frames: depth,
        message:
          `${spread} — a single sub, not a stack, so it will look noisy and ` +
          `speckled. ${next}`,
      };
    }
    return {
      level: "thin",
      frames: depth,
      message: `${spread} — very few, so it will still look noisy. ${next}`,
    };
  }

  if (depth <= 1) {
    return {
      level: "single",
      frames: depth,
      message:
        `This stack combined only ${depth} frame — that's a single sub, ` +
        "not a stack, so it will look noisy and speckled. " + next,
    };
  }
  return {
    level: "thin",
    frames: depth,
    message:
      `This stack combined only ${depth} frames — very few, so it will ` +
      "still look noisy. " + next,
  };
}
