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
