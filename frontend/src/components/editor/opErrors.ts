/** Plain-language warning for editor ops that failed during a full-res export or
 * PNG render. The backend renders full-res best-effort — an op that raises on the
 * full-res data (but worked on the preview proxy, or vice versa) is dropped so it
 * doesn't blank the whole image, but that silently changes the exported look. The
 * export/PNG job result carries the per-op failure messages in `op_errors`; this
 * turns them into a notification body, or null when nothing failed. Pure. */
export function opErrorsMessage(opErrors: unknown): string | null {
  if (!Array.isArray(opErrors)) return null;
  const msgs = opErrors
    .filter((m): m is string => typeof m === "string" && m.trim().length > 0)
    .map((m) => m.trim());
  if (msgs.length === 0) return null;
  const n = msgs.length;
  const head = n === 1 ? "1 operation failed and was skipped" : `${n} operations failed and were skipped`;
  return `${head} in the exported image: ${msgs.join("; ")}`;
}
