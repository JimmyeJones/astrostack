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
//   "These 3 targets look like the same object (Andromeda Galaxy), in separate
//    folders. Combine them into one deeper picture (3.8 h total)."
//
// It used to say "shot on separate nights", which the detection never
// establishes: the backend clusters on plate-solved sky position alone and
// knows nothing about *when* anything was shot. Say what the data supports.
export function describeMergeSuggestion(s: MergeSuggestion): string {
  const n = s.targets.length;
  const obj = s.object_name ? ` (${s.object_name})` : "";
  const total = formatIntegration(mergeSuggestionTotalExposureS(s));
  const totalClause =
    total === "—" ? "" : ` into one deeper picture (${total} total)`;
  return (
    `These ${n} targets look like the same object${obj}, in separate ` +
    `folders. Combine them${totalClause}.`
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

// What to say once the merge has run.
//
// The nudge's fine print promises "nothing is deleted", and the merge does
// delete the source *folders* — so the confirmation has to account for the one
// thing in them a user could not get back: a finished picture. `POST /merge`
// answers `pictures_kept`; an older backend omits it, which reads as "say
// nothing extra" rather than as zero, so the sentence degrades to exactly the
// one this app has always shown.
export function mergeOutcomeMessage(
  nFolders: number,
  label: string,
  picturesKept?: number | null,
): string {
  const kept =
    picturesKept != null && Number.isFinite(picturesKept) && picturesKept > 0
      ? ` Your ${picturesKept} existing picture${picturesKept === 1 ? "" : "s"} ` +
        `came with ${picturesKept === 1 ? "it" : "them"} — see History.`
      : "";
  return (
    `Combined ${nFolders} folders of ${label} into one deep target.` +
    `${kept} Re-stack it to get the deeper picture.`
  );
}
