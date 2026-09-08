import type { StorageInfo } from "../api/client";

/**
 * The Storage page's plain-language sentence about where your raw subs live and
 * who is (not) backing them up.
 *
 * The single largest risk to the owner's pictures is not a bug in this app: his
 * thousands of subs live in `incoming/` and nowhere else, and the page used to
 * say only that the folder was "worth having a backup of" — a generic aside,
 * under the cache table, next to a sentence promising the library could be
 * rebuilt from those files. A beginner reads that as "AstroStack has me
 * covered". This says the actual situation, with his own numbers.
 *
 * Returns `null` when there is nothing honest to say: a fresh install with no
 * ingested frames, or an older backend that doesn't report the counts.
 *
 * `formatBytes` is the caller's own size formatter, so this sentence's "41 GB"
 * matches every other figure on the page exactly.
 */
export function incomingCopyNote(
  info: Pick<StorageInfo, "incoming_frames" | "incoming_bytes"
    | "incoming_unsized_frames" | "incoming_copied">,
  formatBytes: (bytes: number) => string,
): string | null {
  const frames = info.incoming_frames ?? 0;
  if (frames <= 0) return null;

  const bytes = info.incoming_bytes ?? 0;
  const unsized = info.incoming_unsized_frames ?? 0;
  // Rows ingested before the size column existed contribute no bytes, so the
  // total is a floor, not a measurement — say so rather than under-report.
  const size = bytes > 0
    ? ` (${unsized > 0 ? "at least " : ""}${formatBytes(bytes)})`
    : "";
  const subs = frames === 1 ? "sub" : "subs";

  // Both endings say "this is not a backup"; the difference is what the app is
  // actually holding, which the reader can otherwise only guess at.
  const ending = info.incoming_copied
    ? "It reads them from there, and the copies in your cache are working files "
      + "that Clear caches deletes — not a backup."
    : "It reads them where they are and never writes there, and it keeps no copy "
      + "of its own — nothing this app does backs them up.";

  return `Your ${frames.toLocaleString()} ${subs}${size} in incoming/ are the only `
    + `copy AstroStack knows of. ${ending} Keep a copy somewhere else.`;
}
