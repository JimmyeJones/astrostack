// "Same object? Combine these into one deep picture" — pure helpers behind the
// Library nudge. The Seestar app writes a NEW folder per night, so a beginner who
// shoots one object across several nights ends up with several *separate*,
// shallow targets. The backend detects those clusters; these turn one into
// plain-language text and a stable dismissal id.

import type { MergeSuggestion } from "../api/client";
import { formatIntegration } from "../format";

// A stable id for one suggestion group — the sorted member safes joined — so a
// dismissal persists across reloads and the nudge only reappears if the group's
// *membership* changes (e.g. a new same-object folder shows up next clear night).
export function mergeSuggestionSignature(s: MergeSuggestion): string {
  return s.targets.map((t) => t.safe).slice().sort().join("|");
}

// Total accepted-sub exposure across the whole group — what the combined deep
// picture would integrate to.
export function mergeSuggestionTotalExposureS(s: MergeSuggestion): number {
  return s.targets.reduce((sum, t) => sum + (t.total_exposure_s || 0), 0);
}

// Plain-language nudge, e.g.:
//   "These 3 targets look like the same object (Andromeda Galaxy), shot on
//    separate nights. Combine them into one deeper picture (3.8 h total)."
export function describeMergeSuggestion(s: MergeSuggestion): string {
  const n = s.targets.length;
  const obj = s.object_name ? ` (${s.object_name})` : "";
  const total = formatIntegration(mergeSuggestionTotalExposureS(s));
  const totalClause =
    total === "—" ? "" : ` into one deeper picture (${total} total)`;
  return (
    `These ${n} targets look like the same object${obj}, shot on separate ` +
    `nights. Combine them${totalClause}.`
  );
}

// The target the merge folds everything *into* — the deepest-integration member,
// which the backend already sorts first, so it keeps the most history/identity.
export function mergeInto(s: MergeSuggestion): string {
  return s.targets[0]?.safe ?? "";
}

// The remaining members merged *into* the deepest one.
export function mergeSources(s: MergeSuggestion): string[] {
  return s.targets.slice(1).map((t) => t.safe);
}
