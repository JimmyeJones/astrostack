// Library-wide "Target progress" overview: rank every target that has collected
// light by how close it is to a clean image, so a beginner can see at a glance
// which targets are nearly done (worth finishing off) and which already have
// plenty. Reuses the single-source-of-truth readiness verdict from readiness.ts
// (per-object-type goal, honouring any user-set override) — this module only
// orders the list and phrases a friendly summary. A goal is a suggestion, never
// a gate.

import type { TargetProgress } from "./api/client";
import {
  clearNightsFromPace, FINISH_FIRST_MAX_NIGHTS, nightWord,
} from "./components/clearNights";
import { integrationReadiness, type IntegrationReadiness } from "./readiness";
import type { TypeBucket } from "./tonight";

export interface RankedProgress {
  row: TargetProgress;
  readiness: IntegrationReadiness;
  // Clear nights still needed to reach this target's goal at its own recent
  // pace, or null when the goal is already met or there's no usable pace. See
  // ``clearNightsFromPace`` — same arithmetic and wording as the Target page.
  nightsToGo: number | null;
}

// Only targets this close to done are named as "finish this one first" — the
// shared cutoff every compact nights surface uses. Re-exported here because this
// module's own consumers (and their tests) have always imported it from the
// progress card; its definition now lives with the nights arithmetic itself in
// ``components/clearNights``, so the planner can apply the same cap without this
// module and ``readiness`` importing each other.
export { FINISH_FIRST_MAX_NIGHTS };

// A short friendly object-type word ("galaxy"/"nebula"/"cluster") for a
// recognised bucket, so the card can show *why* a target's goal is what it is
// (a galaxy's 6 h vs a cluster's 1.5 h). Returns null for the "Other"/unknown
// bucket — a meaningless "other" label would only add clutter, so the caller
// renders nothing there.
export function objectTypeLabel(bucket: TypeBucket): string | null {
  switch (bucket) {
    case "Galaxy":
      return "galaxy";
    case "Nebula":
      return "nebula";
    case "Cluster":
      return "cluster";
    default:
      return null;
  }
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
    if (!readiness) continue;
    // "How much longer?" only has an answer while there's still a gap to close;
    // once a target has plenty, the level badge says the useful thing instead.
    const gapSeconds = (readiness.goalHours - readiness.hours) * 3600;
    const est =
      readiness.level === "plenty"
        ? null
        : clearNightsFromPace(gapSeconds, row.recent_pace_s);
    ranked.push({ row, readiness, nightsToGo: est ? est.nights : null });
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

/**
 * "Finish this one first" — of the targets still in progress, the one the owner's
 * *own* recent pace says is closest to done, with the number of clear nights it
 * would take.
 *
 * The per-target readiness card answers "how much longer?" on a page you only
 * open once you've already decided what to shoot. The decision itself happens a
 * level up, choosing *between* targets — and a beginner with four half-finished
 * targets has no way to see that one needs a single night and another needs six.
 * This names the one worth finishing, so finishing things is the path of least
 * resistance rather than starting a fifth.
 *
 * Self-hiding by design: nothing to say unless a target is both in progress and
 * within ``FINISH_FIRST_MAX_NIGHTS`` of its goal at its measured pace, and
 * nothing at all when only one target is in play (there is no "first" to pick
 * between one thing — its own card already says it). Ties go to the target
 * furthest along its goal.
 */
export function finishFirstHint(ranked: RankedProgress[]): string | null {
  const inProgress = ranked.filter((r) => r.readiness.level !== "plenty");
  if (inProgress.length < 2) return null;
  const candidates = inProgress.filter(
    (r) => r.nightsToGo !== null && r.nightsToGo <= FINISH_FIRST_MAX_NIGHTS,
  );
  if (candidates.length === 0) return null;
  const best = candidates.reduce((a, b) => {
    if (a.nightsToGo !== b.nightsToGo) {
      return (a.nightsToGo as number) < (b.nightsToGo as number) ? a : b;
    }
    return a.readiness.fraction >= b.readiness.fraction ? a : b;
  });
  const n = best.nightsToGo as number;
  return `Closest to done: ${best.row.name} — about ${n} more clear `
    + `${nightWord(n)} at your recent pace on it.`;
}

/**
 * The compact per-row version of the same figure ("~2 nights"), or null when the
 * row has no usable pace, is already at plenty, or is further out than the cap.
 * Deliberately terse: the row already carries the integration figure and the
 * bar, so this adds the one thing neither of them can say.
 */
export function nightsToGoLabel(r: RankedProgress): string | null {
  if (r.readiness.level === "plenty") return null;
  if (r.nightsToGo === null || r.nightsToGo > FINISH_FIRST_MAX_NIGHTS) return null;
  return `~${r.nightsToGo} more ${nightWord(r.nightsToGo)}`;
}
