import type { MosaicDepthMap, MosaicPanel } from "../../api/client";
import { formatIntegration } from "../../format";

/**
 * Pure helpers behind the "Your mosaic, panel by panel" card.
 *
 * The backend decides *whether* there is a mosaic and *what* to say about it
 * (one engine gate, shared with QC grading, so the app can't hold two opinions
 * about what a panel is). These turn that answer into the grid the card draws.
 */

/** The panels laid out as `rows × cols` cells, `null` where the mosaic has no
 *  panel.
 *
 *  A mosaic isn't always a full rectangle — an L-shaped or stepped one is a
 *  perfectly ordinary thing to shoot — so a cell with nothing in it is drawn as
 *  a gap rather than being squeezed out of the layout, which would move every
 *  other panel away from where it is in the sky. */
export function panelGrid(map: MosaicDepthMap): (MosaicPanel | null)[][] {
  const grid: (MosaicPanel | null)[][] = Array.from(
    { length: Math.max(0, map.rows) },
    () => Array.from({ length: Math.max(0, map.cols) }, () => null),
  );
  for (const p of map.panels) {
    if (p.row >= 0 && p.row < map.rows && p.col >= 0 && p.col < map.cols) {
      grid[p.row][p.col] = p;
    }
  }
  return grid;
}

/** How dark to draw a panel: 0 = the thinnest panel here, 1 = the deepest.
 *
 *  Shaded against this mosaic's own range rather than an absolute scale, because
 *  the question the card answers is comparative ("which corner is behind?") and
 *  a mosaic that is uniformly young would otherwise render as one flat black
 *  square that says nothing. An even mosaic lands everything at the top of the
 *  scale, which reads — correctly — as "nothing is behind". */
export function panelShade(panel: MosaicPanel, map: MosaicDepthMap): number {
  const times = map.panels.map((p) => p.exposure_s).filter(Number.isFinite);
  if (!times.length) return 0;
  const lo = Math.min(...times);
  const hi = Math.max(...times);
  if (!(hi > lo)) return 1;
  return Math.max(0, Math.min(1, (panel.exposure_s - lo) / (hi - lo)));
}

/** "3.1 h over 1,120 subs — the thinnest panel" — one panel's tooltip.
 *
 *  Also the cell's `aria-label`, so the map is readable without a pointer. */
export function panelTooltip(panel: MosaicPanel, map: MosaicDepthMap): string {
  const subs = `${panel.n_frames.toLocaleString()} sub${panel.n_frames === 1 ? "" : "s"}`;
  const thin = map.thin
    && map.thin.row === panel.row && map.thin.col === panel.col;
  return `${formatIntegration(panel.exposure_s)} over ${subs}`
    + (thin ? " — the thinnest panel" : "");
}
