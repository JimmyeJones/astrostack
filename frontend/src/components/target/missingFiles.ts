/** "Your subs aren't on disk" preflight — say it *before* the stack, not after.
 *
 * A frame the library still lists can become unreadable between scans: the
 * Stage-1 cache was cleared while the originals live on a NAS share that is
 * offline, a removable drive was unmounted, the files were moved. Every consumer
 * falls back from the cache to the source and then quietly skips a frame with
 * neither, so the loss is invisible — the stack simply comes out thin, and the
 * user only learns that after walking away for an hour. The reject-summary
 * endpoint now counts them up front (`n_missing_files` over `n_accepted`); this
 * turns that count into the one sentence that names the cause *and* the fix,
 * while the drive is still there to be reconnected.
 *
 * Pure and self-hiding: `null` when nothing is missing, when the counts aren't
 * reported (an older backend omits both fields), or when they're not sane.
 */

export interface MissingFilesNote {
  missing: number;
  total: number;
  title: string;
  message: string;
}

export function missingFilesNote(
  nMissing: number | null | undefined,
  nAccepted: number | null | undefined,
): MissingFilesNote | null {
  if (nMissing == null || !Number.isFinite(nMissing) || nMissing <= 0) return null;
  if (nAccepted == null || !Number.isFinite(nAccepted) || nAccepted <= 0) return null;
  // A snapshot count can't exceed the population it was taken over; clamp rather
  // than render "600 of 500" if the two ever disagree.
  const missing = Math.min(Math.round(nMissing), Math.round(nAccepted));
  const total = Math.round(nAccepted);
  const nf = (n: number) => n.toLocaleString();
  const all = missing >= total;
  return {
    missing,
    total,
    title: all
      ? `This target's ${nf(total)} sub${total === 1 ? "" : "s"} aren't on disk`
      : `${nf(missing)} of ${nf(total)} subs aren't on disk`,
    // Same voice as the after-the-fact note on a finished stack (`missingSubsNote`
    // on the Jobs page), so a user who sees both reads one consistent story.
    message:
      `${all ? "Every one of this target's" : `${nf(missing)} of this target's`} ` +
      `${nf(total)} accepted sub${total === 1 ? " is" : "s are"} listed here, but ` +
      `${missing === 1 ? "its file isn't" : "their files aren't"} on disk right now, ` +
      `so ${missing === 1 ? "it" : "they"} can't be stacked. If they live on a drive ` +
      "or network share, check it's connected, then scan this target again.",
  };
}
