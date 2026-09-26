/** One plain-language label per raw `reject_reason` the app can write.
 *
 * A rejected sub's badge in the frames table (and its tooltip, and the
 * older-backend fallback breakdown) is the one place a beginner reads *why* a
 * frame was left out, so the vocabulary the engine stores — `auto:grade:fwhm_px`,
 * `bulk:streaked`, `auto:file_missing` — has to be turned into a sentence
 * fragment a non-expert recognises.
 *
 * This lived in `routes/Target.tsx`; it is its own module (the `fullres.ts` /
 * `unstretched.ts` pattern) so the one place that owns the wording is greppable
 * from the drift test that keeps it honest — `tests/test_reject_reason_labels.py`
 * derives the vocabulary from the Python that writes it and goes red when a
 * reason here has no label of its own. Two had none: `auto:seestar_output` and
 * `auto:file_missing` both fell through to the generic `auto:` branch and were
 * shown to the owner as their own internal identifier.
 */

/** The grading/QC metric names, in the same words `seestack.qc.grading`'s own
 * `METRIC_LABELS` uses — a frame graded out on `sky_adu_median` is described
 * with one phrase wherever it is described. Pinned against the engine's table
 * by the drift test. */
export const METRIC_LABEL: Record<string, string> = {
  fwhm_px: "FWHM", star_count: "star count",
  eccentricity_median: "eccentricity", sky_adu_median: "sky level",
  transparency_score: "transparency",
};

/** Reasons the app writes **whole**, each with its own label.
 *
 * These are not metrics and not namespaces: they are the app's own decisions
 * about a file, so each needs saying in words rather than being sliced apart.
 * `rejectReasonLabel` consults this table first, so the table and the function
 * cannot come to different answers about one reason.
 */
export const EXACT_LABELS: Record<string, string> = {
  user: "Manual reject",
  "bulk:streaked": "Streaked (bulk)",
  "bulk:trailed": "Trailed (bulk)",
  "auto:streak": "Auto: streak",
  // The Seestar's own finished picture sitting in the same folder as the subs —
  // set aside because it is not a raw frame, which is the app working, not a
  // fault. Said in the words `classify_seestar_junk_target` already uses.
  "auto:seestar_output": "Seestar's own stack",
  // The owner's own "these subs are gone, carry on without them". The
  // reassurance that nothing was deleted by the app belongs to the grouped
  // breakdown's note (`rejection_summary`'s "missing" bucket), not to a badge.
  "auto:file_missing": "File missing",
};

/** The namespaces whose *suffix* is data — a metric name, a solver message, an
 * exception — so they are recognised by prefix rather than listed above. Order
 * matters in `rejectReasonLabel` (the longest namespace wins); this list is the
 * set, and a vitest case proves every entry really is handled. */
export const HANDLED_PREFIXES: readonly string[] = [
  "auto:grade:", "qc:", "bulk:", "auto:", "qc_error", "solve_failed",
];

export function rejectReasonLabel(reason: string): string {
  const exact = EXACT_LABELS[reason];
  if (exact !== undefined) return exact;
  if (reason.startsWith("auto:grade:")) {
    const m = reason.slice(11);
    return `Auto-grade: ${METRIC_LABEL[m] ?? m}`;
  }
  if (reason.startsWith("qc:")) {
    const m = reason.slice(3);
    return `QC: ${METRIC_LABEL[m] ?? m}`;
  }
  if (reason.startsWith("bulk:")) {
    const m = reason.slice(5);
    return `Worst ${METRIC_LABEL[m] ?? m} (bulk)`;
  }
  if (reason.startsWith("auto:")) {
    const m = reason.slice(5);
    return `Auto: ${METRIC_LABEL[m] ?? m}`;
  }
  if (reason.startsWith("qc_error")) return "QC error";
  if (reason.startsWith("solve_failed")) return "Plate-solve failed";
  // Anything else is already a sentence rather than a code: the stacker's own
  // "bad plate-solve (footprint far from the group)" is written for this badge.
  return reason;
}
