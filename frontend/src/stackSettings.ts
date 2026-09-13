// Where a run's *stored settings* and what the stack *actually did* part company.
//
// A finished run records its effective `StackOptions` verbatim (`options_json`),
// and every listing that shows "how was this made" — the Gallery card's
// "Stacking settings" disclosure — dumps that record key by key. That is right
// for almost every key, and wrong for three, because `run_stack` overrides them
// from things the options cannot see:
//
//   * **the canvas.** A union-of-footprints mosaic gets the final gradient
//     removal and the photometric normalization *whether or not they were
//     ticked* (`options.final_gradient_removal or is_mosaic_canvas`, and the
//     same shape for `photometric_normalize`) — panels are shot at different
//     times through different air, and the corrections that run anyway only
//     touch the sky. So a mosaic's card printed "Off" against two passes that
//     had run: measured on the bundled 2x2 sample, whose own run stamps
//     `PHOTNORM` with 18 frames adjusted under a settings row reading "Off".
//   * **the combine.** Min/max rejection is an order statistic and ignores
//     per-frame weights, so a run with `quality_weighted` on can have had the
//     weighting thrown away — which the engine records as `WGTSKIP` and
//     History's run-info panel says in words. Same fact the chip on the same
//     card carries (v0.438.15); this is the row underneath it.
//
// These are *notes on the stored value*, never a replacement for it: the row
// still names the setting, and the sentence says who overrode it and why. Both
// answers stand down to today's wording the moment they are not certain — an
// unknown canvas, an older backend, a run recorded before the column existed.
//
// The mosaic pair is mirrored by hand from the two `or is_mosaic_canvas` gates
// in `seestack/stack/stacker.py`; `tests/test_mosaic_auto_passes_mirror.py`
// reads those gates out of the engine's own source and fails if a third one
// appears, or if either of these stops being automatic.

import { minMaxIgnoresWeighting, weightingUnusedNote } from "./weightingHint";

/** The option keys a mosaic canvas turns on by itself, whatever the run stored. */
export const MOSAIC_AUTO_OPTIONS = [
  "final_gradient_removal",
  "photometric_normalize",
] as const;

const MOSAIC_AUTO_NOTES: Record<string, string> = {
  final_gradient_removal:
    "You didn't tick this, but a mosaic canvas turns it on itself, and this"
    + " picture got it. A mosaic's panels are shot at different times through"
    + " different air, so a masked gradient pass evens the sky across the joins"
    + " without eating the target.",
  photometric_normalize:
    "You didn't tick this, but a mosaic canvas turns it on itself, and this"
    + " picture got it. A panel shot through haze is dimmed all over, which the"
    + " sky corrections leave behind, so the frames are gain-matched — each"
    + " panel against itself, never against its neighbours. It's self-cancelling:"
    + " subs with no usable transparency measurement are left exactly as they are.",
};

/** How a settings row should read when the stack overrode what was stored:
 * the short replacement for the "On"/"Off" column, and the sentence explaining
 * it. `null` means the stored value is the whole truth — say it as it is. */
export interface SettingOverride {
  value: string;
  title: string;
}

export interface SettingContext {
  /** The run's full stored options, so a key can be judged against its siblings. */
  options: Record<string, unknown>;
  /** The run's own mosaic-canvas flag; `null`/`undefined` ⇒ don't claim anything. */
  isMosaic?: boolean | null;
  /** Frames that actually combined — see `minMaxIgnoresWeighting` on why a count
   * that can only *understate* the dispatcher's `n` is the safe one to pass. */
  nFramesUsed?: number | null;
}

export function settingOverride(
  key: string, ctx: SettingContext,
): SettingOverride | null {
  const stored = ctx.options[key];

  // The canvas overrode the switch: it says Off, and it ran anyway.
  if (ctx.isMosaic === true && !stored
      && (MOSAIC_AUTO_OPTIONS as readonly string[]).includes(key)) {
    return { value: "On — automatic", title: MOSAIC_AUTO_NOTES[key] };
  }

  // The combine overrode the switch: it says On, and the weights were ignored.
  if (key === "quality_weighted" && stored && minMaxIgnoresWeighting({
    minMaxReject: !!ctx.options.min_max_reject,
    qualityWeighted: true,
    drizzle: !!ctx.options.drizzle,
    frames: ctx.nFramesUsed ?? null,
  })) {
    return {
      value: "On — not used",
      title: weightingUnusedNote(ctx.nFramesUsed ?? null),
    };
  }

  return null;
}
