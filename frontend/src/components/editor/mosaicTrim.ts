import type { EditOp, OpInstance } from "../../api/client";
import { insertOnCorrectSide } from "./stageConflicts";

/** Fractional (0..1) crop rectangle for the largest well-covered mosaic area. */
export interface TrimCrop {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
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
