import type { OpInstance } from "../../api/client";
import type { HistGuide } from "./Histogram";

/** Vertical guides to overlay on the editor histogram when a `tone.levels` op is
 * selected, so a beginner can see *where* the black/white points they're setting
 * land on the tonal range (relative to the sky peak and the highlights they clip).
 *
 * Draws the current black and white points as solid lines, plus — when a
 * data-driven suggestion is available and differs from the current value — a faint
 * dashed marker at each suggested point (the same values the "Auto levels" / "From
 * your image" buttons apply), so the user can see the recommendation on the graph.
 *
 * Pure and returns `[]` for any non-Levels selection (or none), so the caller can
 * always spread it into the histogram's `guides` prop. */
export function levelsHistGuides(
  selectedOp: OpInstance | null,
  suggestion?: { black: number; white: number } | null,
): HistGuide[] {
  if (!selectedOp || selectedOp.id !== "tone.levels") return [];
  const black = Number(selectedOp.params?.black ?? 0);
  const white = Number(selectedOp.params?.white ?? 1);
  const guides: HistGuide[] = [];
  if (Number.isFinite(black)) guides.push({ value: black, color: "#adb5bd", label: "B" });
  if (Number.isFinite(white)) guides.push({ value: white, color: "#f1f3f5", label: "W" });
  if (suggestion) {
    // Only show a suggestion marker where it differs from the current point, so a
    // point already at its suggestion isn't cluttered by a redundant dashed line.
    if (Number.isFinite(suggestion.black) && Math.abs(suggestion.black - black) > 1e-6) {
      guides.push({ value: suggestion.black, color: "#4dabf7", dashed: true });
    }
    if (Number.isFinite(suggestion.white) && Math.abs(suggestion.white - white) > 1e-6) {
      guides.push({ value: suggestion.white, color: "#4dabf7", dashed: true });
    }
  }
  return guides;
}
