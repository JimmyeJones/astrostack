import type { EditOp, OpInstance } from "../../api/client";
import { insertOnCorrectSide } from "./stageConflicts";

/** Fractional (0..1) crop rectangle for the largest well-covered mosaic area. */
export interface TrimCrop {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** True when the recipe has an *enabled* geometry op (crop/rotate/resize) that
 * reshapes the frame — so the raw, full-frame coverage overlay no longer lines
 * up with the (reshaped) edited preview. Pure. */
export function hasEnabledGeometryOp(ops: OpInstance[]): boolean {
  return ops.some((o) => o.enabled && o.id.startsWith("geometry."));
}

/** CSS `left/top/width/height` (percent strings) placing the proposed-crop
 * rectangle over the preview image, from the fractional bounds. Pure. */
export function trimRectStyle(
  crop: TrimCrop,
): { left: string; top: string; width: string; height: string } {
  const pct = (v: number) => `${(v * 100).toFixed(2)}%`;
  return {
    left: pct(crop.x0),
    top: pct(crop.y0),
    width: pct(crop.x1 - crop.x0),
    height: pct(crop.y1 - crop.y0),
  };
}

/** Inline style for the preview *image box* — a wrapper sized to exactly the
 * displayed image so a percentage overlay (the proposed-crop rectangle) lines
 * up even when the preview is letterboxed.
 *
 * The preview `<img>` is width-100% but height-capped at ~62vh, so on a tall
 * (portrait) frame or a short window it pillarboxes inside its element and a
 * rectangle placed as a percentage of the *container* lands offset. Giving the
 * wrapper the image's own aspect ratio and capping its width so the
 * aspect-preserved height never exceeds the same cap makes the box equal the
 * shown image (no letterbox), so `trimRectStyle` percentages map straight onto
 * it. Falls back to plain full-width when the proxy dimensions are unknown
 * (histogram not loaded yet) — same as the old behaviour. Pure.
 */
export function previewBoxStyle(
  proxyWidth: number | undefined,
  proxyHeight: number | undefined,
  maxHeightVh = 62,
): { width: string; maxHeight?: string; maxWidth?: string; aspectRatio?: string; margin?: string } {
  if (!proxyWidth || !proxyHeight || proxyWidth <= 0 || proxyHeight <= 0
      || !Number.isFinite(proxyWidth) || !Number.isFinite(proxyHeight)) {
    return { width: "100%", maxHeight: `${maxHeightVh}vh` };
  }
  return {
    width: "100%",
    maxWidth: `calc(${maxHeightVh}vh * ${proxyWidth} / ${proxyHeight})`,
    aspectRatio: `${proxyWidth} / ${proxyHeight}`,
    margin: "0 auto",
  };
}

/** Plain-language "keeps the central W% × H%" summary of a proposed crop. Pure. */
export function trimKeptLabel(crop: TrimCrop): string {
  const pctW = Math.round((crop.x1 - crop.x0) * 100);
  const pctH = Math.round((crop.y1 - crop.y0) * 100);
  return `keeps the central ${pctW}% × ${pctH}%`;
}

/** Set (or add) a `geometry.crop` op to the given fractional bounds — the
 * one-click "trim the ragged mosaic border" action. If a crop op already exists
 * it's updated in place and enabled (so re-trimming never stacks duplicate crops);
 * otherwise a fresh crop op is inserted on the correct side of the stretch. Pure:
 * returns a new ops array and never mutates the input. */
export function applyTrimCrop(
  ops: OpInstance[],
  crop: TrimCrop,
  specs: Record<string, EditOp>,
  makeUid: () => string,
): OpInstance[] {
  const bounds = { x0: crop.x0, y0: crop.y0, x1: crop.x1, y1: crop.y1 };
  if (ops.some((o) => o.id === "geometry.crop")) {
    return ops.map((o) =>
      o.id === "geometry.crop"
        ? { ...o, enabled: true, params: { ...o.params, ...bounds } }
        : o,
    );
  }
  const spec = specs["geometry.crop"];
  const defaults: Record<string, unknown> = {};
  spec?.params.forEach((p) => { defaults[p.key] = p.default; });
  const op: OpInstance = {
    uid: makeUid(),
    id: "geometry.crop",
    enabled: true,
    params: { ...defaults, ...bounds },
  };
  // With the crop spec known we can place it correctly (nonlinear → after the
  // stretch); without it (schema not loaded) fall back to appending.
  return spec ? insertOnCorrectSide(ops, op, specs) : [...ops, op];
}
