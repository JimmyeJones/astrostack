import type { CalibrationCoverage } from "../api/client";

// Plain-language copy for the Calibration page's "do my masters actually cover my
// targets?" roll-up. The page lists the masters you've built but never connects
// them back to the library, so a beginner who built one 30 s dark has no idea it
// covers four of their six targets and misses the two they shot at 10 s (or the
// ones from a second Seestar) — today they find that out target-by-target, on the
// Stack form or after an uncalibrated result.
//
// "Covers" is the *unattended* binder's own confidence test (see
// `calibration.master_coverage`), so these lines promise exactly what the app will
// do on its own — never something the user would still have to pick by hand.
//
// Kept pure and separate from the page so the wording is unit-tested.

type MasterRow = CalibrationCoverage["masters"][number];

/** The per-master coverage line, or null when there's nothing to say (a library
 *  with no targets yet — "covers 0 of your 0 targets" would just be noise). */
export function masterCoverageLine(
  row: Pick<MasterRow, "n_covered">,
  nTargets: number,
): string | null {
  if (nTargets <= 0) return null;
  const targets = nTargets === 1 ? "target" : "targets";
  if (row.n_covered === 0) {
    return `Doesn't match any of your ${nTargets} ${targets} yet`;
  }
  if (row.n_covered >= nTargets) {
    return `Covers all ${nTargets} of your ${targets}`;
  }
  return `Covers ${row.n_covered} of your ${nTargets} ${targets}`;
}

/** The targets this master can't be applied to, as tooltip copy — or null when it
 *  covers everything (nothing to explain) or there are no targets at all. */
export function masterMissesTooltip(
  row: Pick<MasterRow, "missed">,
  nTargets: number,
): string | null {
  if (nTargets <= 0 || row.missed.length === 0) return null;
  return `Can't be applied to: ${row.missed.join(", ")}`;
}

/** The gentle nudge for targets no master reaches at all — the gap that actually
 *  costs the user picture quality. Null when everything is covered (or there's
 *  nothing to cover), so the page stays quiet when there's no problem. */
export function uncoveredTargetsNote(
  coverage: Pick<CalibrationCoverage, "uncovered" | "n_targets" | "auto_apply">,
): string | null {
  const { uncovered, n_targets: nTargets } = coverage;
  if (nTargets <= 0 || uncovered.length === 0) return null;
  const names = uncovered.join(", ");
  const lead = uncovered.length === 1
    ? `${names} has no matching master yet`
    : `${uncovered.length} of your ${nTargets} targets have no matching master `
      + `yet (${names})`;
  // Only promise hands-off use when auto-calibration is actually on; with it off
  // (the default) a matching master still has to be picked on the Stack form, and
  // saying otherwise would be a promise the app doesn't keep.
  const then = coverage.auto_apply
    ? "and AstroStack will apply it for you"
    : "then pick it on the Stack form (or turn on auto-calibration in Settings "
      + "to have it applied for you)";
  return (
    `${lead} — build a dark from frames shot the same way (same exposure, gain `
    + `and camera), ${then}.`
  );
}
