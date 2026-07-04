import type { Histogram, OpInstance } from "../../api/client";
import type { HistGuide } from "./Histogram";
import { levelsHistGuides } from "./levelsGuides";
import { clippingEdges } from "./clipping";

/** Vertical guides marking the interior control points of a selected `tone.curves`
 * op on the histogram, so a beginner can see *where on the tonal range* each bend
 * of their curve lands (is it sitting on the sky peak, the midtones, the
 * highlights?). The curve's input is the display value — the histogram's own
 * x-axis — so a control point at input x maps straight to a vertical guide at x.
 *
 * The two endpoints (x=0 and x=1) are omitted: they're locked there and coincide
 * with the clip edges the clipping guides already mark, so drawing them would just
 * clutter the graph. Returns `[]` for any non-Curves selection. Pure. */
export function curvesHistGuides(selectedOp: OpInstance | null): HistGuide[] {
  if (!selectedOp || selectedOp.id !== "tone.curves") return [];
  const raw = selectedOp.params?.points;
  if (!Array.isArray(raw)) return [];
  const guides: HistGuide[] = [];
  for (const p of raw) {
    if (!Array.isArray(p) || p.length < 1) continue;
    const x = Number(p[0]);
    // Interior points only (endpoints are pinned at 0/1 and shown as clip edges).
    if (Number.isFinite(x) && x > 1e-6 && x < 1 - 1e-6) {
      guides.push({ value: x, color: "#cc5de8", dashed: true });
    }
  }
  return guides;
}

/** Vertical guides at the histogram's clipping edges — value 0 (pure black) when
 * the shadows are crushing and value 1 (pure white) when the highlights are
 * blowing — using the exact same detection as the clipping caption, so whenever
 * the caption warns about a clip the graph also shows which edge it lands on.
 * Advisory only. Returns `[]` when nothing is clipping. Pure. */
export function clippingHistGuides(hist: Histogram | undefined): HistGuide[] {
  const { high, low } = clippingEdges(hist);
  const guides: HistGuide[] = [];
  if (low) guides.push({ value: 0, color: "#fd7e14", label: "clip" });
  if (high) guides.push({ value: 1, color: "#fd7e14", label: "clip" });
  return guides;
}

/** All the tonal guides to overlay on the editor histogram: the Levels op's
 * black/white points (and their data-driven suggestion) when a Levels op is
 * selected, the interior control points of a selected Curves op, and the clip
 * edges whenever the recipe is clipping. Composes the three pure helpers so a
 * single call feeds the histogram's `guides` prop, and *every* tonal control
 * shows where it lands on the graph — not just Levels. Pure. */
export function tonalHistGuides(
  selectedOp: OpInstance | null,
  levelsSuggestion: { black: number; white: number } | null | undefined,
  hist: Histogram | undefined,
): HistGuide[] {
  return [
    ...levelsHistGuides(selectedOp, levelsSuggestion),
    ...curvesHistGuides(selectedOp),
    ...clippingHistGuides(hist),
  ];
}
