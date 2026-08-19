/** "Your subs aren't on disk" — said once for the whole library, not once per target.
 *
 * The Target page already warns when *that* target's accepted subs have no file
 * behind them any more (`missingFilesNote`). But the cause almost never stops at
 * one target: an unmounted drive or an offline NAS share takes out every target
 * at once, and the owner would have to open each one in turn to discover the
 * scale of it. `GET /api/library/missing-files` counts the whole library in one
 * cached pass; this turns that count into the one sentence that names the cause
 * *and* the fix, on the page they land on first.
 *
 * Pure and self-hiding: `null` when nothing is missing, when the payload is
 * absent (an older backend has no such endpoint), or when the numbers aren't
 * sane. Same voice as the per-target note and as the after-the-fact note on a
 * finished stack, so someone who sees two of them reads one consistent story.
 */

import type { LibraryMissingFiles } from "../../api/client";

export interface LibraryMissingFilesNote {
  missing: number;
  targets: number;
  title: string;
  message: string;
  /** The one affected target's `safe_name`, when exactly one is affected — so
   *  the note can link straight at it. `null` whenever it would be a guess. */
  onlyTargetSafe: string | null;
}

export function libraryMissingFilesNote(
  data: LibraryMissingFiles | null | undefined,
): LibraryMissingFilesNote | null {
  if (!data) return null;
  const raw = data.n_missing;
  if (raw == null || !Number.isFinite(raw) || raw <= 0) return null;
  const missing = Math.round(raw);
  // `targets` is a *capped* worst-first list (a library-wide outage affects
  // every target, and the note only ever names one), so the count comes from
  // the separate total. Fall back to the list length, then to "at least one",
  // rather than printing "across 0 targets".
  const affected = Array.isArray(data.targets) ? data.targets : [];
  const counted = data.n_targets_missing;
  const targets = Math.max(
    Number.isFinite(counted) ? Math.round(counted as number) : affected.length,
    affected.length,
    1,
  );
  const only = targets === 1 ? affected[0] ?? null : null;
  const nf = (n: number) => n.toLocaleString();
  const subs = `sub${missing === 1 ? "" : "s"}`;
  const verb = missing === 1 ? "isn't" : "aren't";
  const title = only?.name
    ? `${nf(missing)} of ${only.name}'s ${subs} ${verb} on disk`
    : targets === 1
      ? `${nf(missing)} ${subs} ${verb} on disk`
      : `${nf(missing)} ${subs} across ${nf(targets)} targets ${verb} on disk`;
  return {
    missing,
    targets,
    onlyTargetSafe: only?.safe ?? null,
    title,
    message:
      `${missing === 1 ? "It's" : "They're"} listed in your library, but ` +
      `${missing === 1 ? "its file isn't" : "their files aren't"} on disk right now, ` +
      `so ${missing === 1 ? "it" : "they"} can't be stacked. That usually means a ` +
      "drive or network share is offline — check it's connected, then scan again.",
  };
}
