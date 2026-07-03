import type { EditOp, OpInstance } from "../../api/client";

export const LEVEL_COVERAGE_ID = "background.level_coverage";

/** Prepend a Coverage-leveling op to a recipe when the run is a mosaic.
 *
 * On a mosaic (uneven panel overlap → coverage spans a range) equalising the
 * per-panel sky before anything else flattens the visible panel steps — the same
 * pass the one-click Auto recipe now prepends. Built-in presets carry a fixed op
 * list that doesn't know whether *this* stack is a mosaic, so we add it at apply
 * time. The op is a linear pass, so it belongs at the very front, before the
 * preset's gradient/colour ops.
 *
 * Pure and non-mutating. Returns the input unchanged when the run isn't a mosaic,
 * the op isn't in the schema, or the recipe already contains a leveling pass (so
 * re-applying a preset never stacks duplicates).
 */
export function prependCoverageLeveling(
  ops: OpInstance[],
  isMosaic: boolean,
  specs: Record<string, EditOp>,
  mkUid: () => string,
): OpInstance[] {
  if (!isMosaic) return ops;
  const spec = specs[LEVEL_COVERAGE_ID];
  if (!spec) return ops;
  if (ops.some((o) => o.id === LEVEL_COVERAGE_ID)) return ops;
  const params: Record<string, unknown> = {};
  spec.params.forEach((p) => { params[p.key] = p.default; });
  return [{ uid: mkUid(), id: LEVEL_COVERAGE_ID, enabled: true, params }, ...ops];
}
