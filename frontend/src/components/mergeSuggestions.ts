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

// The two clauses every "we combined it" confirmation owes the user, shared so
// the app's **two** Combine buttons cannot describe one operation differently.
//
// The Library nudge ("these look like the same object") has said both since
// v0.480.x. The Library's *cleanup* card — which is where the duplicate-target
// reconciliation is offered, and therefore the button an owner with historical
// duplicates actually presses — ran the identical `POST /api/targets/merge` and
// threw the answer away, so the same operation reported a pinned cover on one
// screen and stayed silent about it on the other.

// "…and your finished pictures came too." The nudge's fine print promises
// "nothing is deleted", and the merge does delete the source *folders* — so a
// confirmation has to account for the one thing in them a user could not get
// back. `POST /merge` answers `pictures_kept`; an older backend omits it, which
// reads as "say nothing extra" rather than as zero.
export function mergeKeptClause(picturesKept?: number | null): string {
  if (picturesKept == null || !Number.isFinite(picturesKept) || picturesKept <= 0) {
    return "";
  }
  return (
    ` Your ${picturesKept} existing picture${picturesKept === 1 ? "" : "s"} ` +
    `came with ${picturesKept === 1 ? "it" : "them"} — see History.`
  );
}

// "…and it kept showing its own picture." A carried picture is usually the
// *newest* one, so the backend pins the deep target's own picture as its cover
// to stop a one-night stack replacing it. That is a visible change to the
// target — and one nobody asked for by name — so say it rather than leave a
// cover the user never pinned to be discovered later. Absent ⇒ older backend ⇒
// say nothing.
export function mergeCoverClause(picturePinned?: boolean | null): string {
  return picturePinned ? " It still shows its own picture, kept as the cover." : "";
}

// What to say once the nudge's merge has run.
export function mergeOutcomeMessage(
  nFolders: number,
  label: string,
  picturesKept?: number | null,
  picturePinned?: boolean | null,
): string {
  return (
    `Combined ${nFolders} folders of ${label} into one deep target.` +
    `${mergeKeptClause(picturesKept)}${mergeCoverClause(picturePinned)}` +
    ` Re-stack it to get the deeper picture.`
  );
}
