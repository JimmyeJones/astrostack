/**
 * What the "TIFF" download actually opens as.
 *
 * Every other item on History's artifact menu carries a one-line hint saying
 * what the file is — and TIFF, the one that most needs it, had none. A plain
 * stack's TIFF is written **linear** (`_write_tiff`'s `mode="linear"`, which is
 * `StackOptions.tiff_mode`'s default), so a beginner who picks the
 * biggest-sounding file gets sixteen bits of raw levels that open near-black in
 * any ordinary viewer and read as a broken download.
 *
 * The honest sentence isn't one sentence, though: the same menu item serves an
 * **editor export**, whose TIFF is written from the recipe's already tone-mapped
 * result and opens looking exactly like the picture on screen. So the copy has
 * to know which — and it can, from facts the run already carries in its own
 * `options_json`, with no new API field and no second read:
 *
 * * `display_space: true` — written by the editor export in the *same* call
 *   that passes `already_display=True` to `write_stack_outputs`, so the two can't
 *   disagree. It is also what the server's own `_run_display_space` reads.
 * * `tiff_mode: "autostretch"` — the stacker's other TIFF mode, which bakes the
 *   export stretch in.
 *
 * Anything else — including a run whose options are missing or unparseable — is
 * the linear default, which is both the common case and the safe thing to say:
 * warning that a file may open dark costs a stretched picture nothing, while
 * staying silent costs a linear one the whole download.
 */

/** Does this run's TIFF open looking like the picture the app shows? */
export function tiffOpensAsShown(options?: Record<string, unknown> | null): boolean {
  if (!options) return false;
  if (options.display_space === true) return true;
  return options.tiff_mode === "autostretch";
}

/** The dimmed one-line hint under the TIFF item. */
export function tiffDownloadHint(options?: Record<string, unknown> | null): string {
  return tiffOpensAsShown(options)
    ? "16-bit — the finished picture, at full depth"
    : "16-bit raw levels — opens dark until you stretch it in another app";
}
