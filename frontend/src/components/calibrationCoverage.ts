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
 *  covers everything (nothing to explain) or there are no targets at all.
 *
 *  When the backend says *why* each one misses (`missed_detail`, v0.218+), each
 *  target gets its own line naming the blocker — "M 13 — your subs are 10s, this
 *  dark is 30s" — which is the difference between a list the user can only read
 *  and one they can act on. An older backend sends only the names, so the bare
 *  comma list stays as the fallback. */
export function masterMissesTooltip(
  row: Pick<MasterRow, "missed"> & Partial<Pick<MasterRow, "missed_detail">>,
  nTargets: number,
): string | null {
  if (nTargets <= 0 || row.missed.length === 0) return null;
  const detail = (row.missed_detail ?? []).filter((d) => d?.name && d?.reason);
  if (detail.length === 0) return `Can't be applied to: ${row.missed.join(", ")}`;
  const lines = detail.map((d) => `${d.name} — ${d.reason}`);
  return `Can't be applied to:\n${lines.join("\n")}`;
}

/** The gentle nudge for targets no master reaches at all — the gap that actually
 *  costs the user picture quality. Null when everything is covered (or there's
 *  nothing to cover), so the page stays quiet when there's no problem. */
export function uncoveredTargetsNote(
  coverage: Pick<CalibrationCoverage, "uncovered" | "n_targets" | "auto_apply">
    & Partial<Pick<CalibrationCoverage, "uncovered_detail">>,
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
    + `and camera), ${then}.${uncoveredDarkSpecHint(coverage.uncovered_detail)}`
  );
}

/** "Shot the same way" is only actionable if you know *which* way. This turns the
 *  uncovered targets' own recorded exposure/gain into the numbers to shoot at —
 *  one spec when they agree, an honest "different settings" list when they don't
 *  (one dark can't cover both). Empty string when nothing was recorded, so the
 *  nudge degrades to its generic wording rather than inventing a number. */
export function uncoveredDarkSpecHint(
  detail: CalibrationCoverage["uncovered_detail"],
): string {
  const specs = new Map<string, string>();
  for (const d of detail ?? []) {
    if (!d || d.exposure_s == null || !(d.exposure_s > 0)) continue;
    const exp = `${Number(d.exposure_s.toFixed(3))}s`;
    const label = d.gain == null ? exp : `${exp} at gain ${Number(d.gain)}`;
    specs.set(label, label);
  }
  const labels = [...specs.values()];
  if (labels.length === 0) return "";
  if (labels.length === 1) {
    return ` Shoot them at ${labels[0]} — that's what those subs were shot at.`;
  }
  return (
    ` Those subs weren't all shot the same way (${labels.join("; ")}), so they `
    + `need a dark each — one dark only matches subs shot at its own settings.`
  );
}
