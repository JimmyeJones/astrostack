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
  row: Pick<MasterRow, "n_covered"> & Partial<Pick<MasterRow, "n_partial">>,
  nTargets: number,
): string | null {
  if (nTargets <= 0) return null;
  const targets = nTargets === 1 ? "target" : "targets";
  if (row.n_covered === 0) {
    return `Doesn't match any of your ${nTargets} ${targets} yet`;
  }
  if (row.n_covered >= nTargets) {
    return `Covers all ${nTargets} of your ${targets}${partialClause(row)}`;
  }
  return `Covers ${row.n_covered} of your ${nTargets} ${targets}${partialClause(row)}`;
}

/** " — one only partly" / " — 2 only partly", or "" when there is nothing to say.
 *
 *  A target is one *folder*, never one exposure: shoot it at 10 s one night and
 *  30 s the next and the binder reduces it to a median, so a 20 s dark can be
 *  bound to a target not one of whose frames it matches. "Covers all 3 of your
 *  targets" was true about the binding and misleading about the pictures. */
function partialClause(row: Partial<Pick<MasterRow, "n_partial">>): string {
  const n = row.n_partial ?? 0;
  if (n <= 0) return "";
  return n === 1 ? " — one only partly" : ` — ${n} only partly`;
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

/** The targets this master is bound to but only *partly* reaches, as tooltip
 *  copy — or null when there are none (so the page stays quiet on the ordinary
 *  single-exposure library, which is every library until someone changes their
 *  sub length between nights).
 *
 *  Kept separate from `masterMissesTooltip` because it is a different claim: a
 *  missed target gets nothing from this master, a partly-covered one gets a dark
 *  that is right for some of its subs and wrong for the rest. Both can be true of
 *  one master at once, and the page joins them. */
export function masterPartialTooltip(
  row: Partial<Pick<MasterRow, "partial_detail">>,
): string | null {
  const detail = (row.partial_detail ?? []).filter((d) => d?.name && d?.reason);
  if (detail.length === 0) return null;
  return `Only part of:\n${detail.map((d) => d.reason).join("\n")}`;
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
    if (!d) continue;
    // A target's *own* sub lengths when the backend sends them, the median it
    // used to send otherwise. This is the difference between "shoot them at 20s"
    // — a length no sub on an evenly split 10 s / 30 s target was shot at — and
    // an honest "these need a dark each".
    const lengths = (d.exposures_s ?? []).filter((e) => e != null && e > 0);
    const from = lengths.length > 0
      ? lengths
      : (d.exposure_s != null && d.exposure_s > 0 ? [d.exposure_s] : []);
    for (const e of from) {
      const exp = `${Number(e.toFixed(3))}s`;
      const label = d.gain == null ? exp : `${exp} at gain ${Number(d.gain)}`;
      specs.set(label, label);
    }
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
