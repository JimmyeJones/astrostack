// Library-wide "Target progress" overview: rank every target that has collected
// light by how close it is to a clean image, so a beginner can see at a glance
// which targets are nearly done (worth finishing off) and which already have
// plenty. Reuses the single-source-of-truth readiness verdict from readiness.ts
// (per-object-type goal, honouring any user-set override) — this module only
// orders the list and phrases a friendly summary. A goal is a suggestion, never
// a gate.

import type { TargetProgress } from "./api/client";
import { integrationReadiness, type IntegrationReadiness } from "./readiness";

export interface RankedProgress {
  row: TargetProgress;
  readiness: IntegrationReadiness;
}

// Rank targets so the ones that most reward more imaging time lead: any target
// not yet at "plenty" comes first (nearest-to-goal first, so the "almost there"
// targets a beginner should finish off surface at the top), then the targets
// that already have plenty (most-integrated first).
export function rankLibraryProgress(rows: TargetProgress[]): RankedProgress[] {
  const ranked: RankedProgress[] = [];
  for (const row of rows) {
    const readiness = integrationReadiness(
      row.total_exposure_s,
      row.object_type,
      row.goal_s == null ? null : row.goal_s / 3600,
    );
    // integrationReadiness only returns null at zero integration, which the
    // backend already excludes — but guard defensively so a stray row is
    // dropped rather than crashing the card.
    if (readiness) ranked.push({ row, readiness });
  }
  ranked.sort((a, b) => {
    const aDone = a.readiness.level === "plenty";
    const bDone = b.readiness.level === "plenty";
    if (aDone !== bDone) return aDone ? 1 : -1; // in-progress before plenty
    if (aDone) return b.readiness.hours - a.readiness.hours; // plenty: most first
    return b.readiness.fraction - a.readiness.fraction; // in-progress: closest first
  });
  return ranked;
}

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

// A plain-language one-liner over the ranked list, e.g. "2 targets could use
// more time; 1 has plenty for a clean image." Returns "" for an empty list so
// the caller renders nothing.
export function describeLibraryProgress(ranked: RankedProgress[]): string {
  if (ranked.length === 0) return "";
  const done = ranked.filter((r) => r.readiness.level === "plenty").length;
  const inProgress = ranked.length - done;
  if (inProgress === 0) {
    return `All ${done} ${plural(done, "target has", "targets have")} plenty of `
      + "integration for a clean image.";
  }
  if (done === 0) {
    return `${inProgress} ${plural(inProgress, "target is", "targets are")} in progress`
      + " — keep shooting to reach a clean image.";
  }
  return `${inProgress} ${plural(inProgress, "target", "targets")} could use more time; `
    + `${done} ${plural(done, "has", "have")} plenty for a clean image.`;
}
