/**
 * What to say when auto-grade's list was truncated by a safety rail.
 *
 * The grader has **two** 25% rails and they are not the same thing:
 *
 * * the **target-wide** rail — more than a quarter of the whole target was
 *   flagged. That genuinely is "this looks like a rough session", and a
 *   conservative pass (a higher z threshold) really would shorten the list.
 * * the **per-panel** rail — a mosaic panel would have lost more than a quarter
 *   of *its own* subs. That is a **count limit on one patch of sky**, and the
 *   target-wide advice is wrong for it twice over: a conservative pass *shrinks*
 *   the flagged set and so can never release a frame a count limit withheld, and
 *   "review the night's data" points at a night when the withheld frames are
 *   concentrated on panels.
 *
 * Until v0.474.0 one boolean carried both and every surface told the
 * target-wide story. On the owner's library that made the notice false on
 * **7 of his 21 capped targets** — targets that flagged too few frames to have
 * reached the target-wide rail at all, one of them raising the orange "rough
 * session" banner off a **single** withheld frame at an 8.0% flag rate
 * (observer issue #968). He is a heavy mosaic user, so those are his targets.
 */
import type { GradeReport } from "./api/client";

export type GradeCapKind = "session" | "panels" | "both";

export interface GradeCapNotice {
  kind: GradeCapKind;
  /** One self-contained sentence (or two), usable inline or in an Alert. */
  text: string;
}

const SESSION =
  "This looks like a rough session — more frames were flagged than the 25% " +
  "safety cap allows, so only the worst are listed. Consider a conservative " +
  "pass first, or review the night's data.";

function panelSentence(withheld: number, panels: number): string {
  const f = withheld === 1 ? "1 flagged frame" : `${withheld} flagged frames`;
  const p = panels === 1 ? "1 mosaic panel" : `${panels} mosaic panels`;
  const was = withheld === 1 ? "was" : "were";
  return (
    `${f} on ${p} ${was} held back so no panel loses more than a quarter of ` +
    "its own subs. That's a limit per panel, not a rough night — a " +
    "conservative pass won't release them; look at those panels instead."
  );
}

/**
 * The notice for this report, or `null` when nothing was capped.
 *
 * An older backend sends `capped` alone, with neither breakdown field: that is
 * read as the target-wide case, which is exactly what those installs showed
 * before — so the copy never regresses on an upgrade in either direction.
 */
export function gradeCapNotice(
  report: Pick<
    GradeReport,
    "capped" | "capped_overall" | "capped_panels" | "withheld_per_panel"
  > | null | undefined,
): GradeCapNotice | null {
  if (!report?.capped) return null;
  const panels = report.capped_panels ?? 0;
  const withheld = report.withheld_per_panel ?? 0;
  // The breakdown is absent on an older backend; `capped` alone still means
  // what it always did there.
  const overall = report.capped_overall ?? true;
  if (panels > 0 && withheld > 0) {
    if (overall) {
      return {
        kind: "both",
        text:
          "More frames were flagged than the 25% safety cap allows, so only " +
          `the worst are listed — and ${panelSentence(withheld, panels)}`,
      };
    }
    return { kind: "panels", text: panelSentence(withheld, panels) };
  }
  return { kind: "session", text: SESSION };
}
