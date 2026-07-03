import type { EditOp, OpInstance } from "../../api/client";

/** The editor pipeline runs ops in order across a single stretch boundary: ops
 * declaring `stage:"linear"` must run *before* the stretch (they expect linear,
 * un-stretched data — background/gradient removal, colour calibration, denoise,
 * deconvolution, …), while `stage:"nonlinear"` ops must run *after* it (they work
 * in display space `[0,1]` — curves, levels, saturation, sharpen, star ops, …).
 * `stage:"any"` ops (and the stretch itself) are valid on either side.
 *
 * The op list lets a user drag ops anywhere, so it's easy to end up with e.g. a
 * background-gradient op below the stretch, where it silently misbehaves. These
 * pure helpers flag that so the UI can warn and offer a one-click fix. */

export type WrongStage = "linear" | "nonlinear";

/** True when at least one *enabled* op is the stretch boundary. When false the
 * pipeline silently auto-inserts a default asinh stretch at the end, so the UI
 * can nudge the user to add an explicit, controllable stretch. */
export function hasEnabledStretch(
  ops: OpInstance[],
  specs: Record<string, EditOp>,
): boolean {
  return ops.some((o) => o.enabled && specs[o.id]?.is_stretch);
}

/** Map of op uid -> the (mis-placed) stage, for every *enabled* op sitting on the
 * wrong side of an *enabled* stretch op. Empty when there's no explicit stretch
 * boundary (nothing to check against) or nothing conflicts. */
export function stageConflicts(
  ops: OpInstance[],
  specs: Record<string, EditOp>,
): Record<string, WrongStage> {
  const out: Record<string, WrongStage> = {};
  const stretchIdx = ops.findIndex((o) => o.enabled && specs[o.id]?.is_stretch);
  if (stretchIdx < 0) return out;
  ops.forEach((op, i) => {
    if (!op.enabled || i === stretchIdx) return;
    const stage = specs[op.id]?.stage;
    if (stage === "linear" && i > stretchIdx) out[op.uid] = "linear";
    else if (stage === "nonlinear" && i < stretchIdx) out[op.uid] = "nonlinear";
  });
  return out;
}

/** Return a new op list with a freshly-added `op` inserted on the correct side of
 * the enabled stretch: `linear` ops just before it, `nonlinear` ops just after it.
 * Falls back to appending at the end when there's no enabled stretch or the op's
 * stage isn't a hard side (`any`), matching the plain "add at the end" behaviour —
 * so the common add-then-tune flow never lands an op on the wrong side of the
 * stretch (which would immediately trip the stage-conflict caution). */
export function insertOnCorrectSide(
  ops: OpInstance[],
  op: OpInstance,
  specs: Record<string, EditOp>,
): OpInstance[] {
  const stage = specs[op.id]?.stage;
  if (stage !== "linear" && stage !== "nonlinear") return [...ops, op];
  const s = ops.findIndex((o) => o.enabled && specs[o.id]?.is_stretch);
  if (s < 0) return [...ops, op];
  const at = stage === "linear" ? s : s + 1;
  const next = [...ops];
  next.splice(at, 0, op);
  return next;
}

/** Return a new op list with `uid` moved to the correct side of the enabled
 * stretch: `linear` ops just before it, `nonlinear` ops just after it. A no-op
 * (returns the same array) when there's no enabled stretch, the op is missing, or
 * the op's stage isn't a hard side (`any`). */
export function moveToCorrectSide(
  ops: OpInstance[],
  uid: string,
  specs: Record<string, EditOp>,
): OpInstance[] {
  const i = ops.findIndex((o) => o.uid === uid);
  if (i < 0) return ops;
  const stage = specs[ops[i].id]?.stage;
  if (stage !== "linear" && stage !== "nonlinear") return ops;
  const op = ops[i];
  const rest = ops.filter((o) => o.uid !== uid);
  const s = rest.findIndex((o) => o.enabled && specs[o.id]?.is_stretch);
  if (s < 0) return ops;
  const at = stage === "linear" ? s : s + 1;
  const next = [...rest];
  next.splice(at, 0, op);
  return next;
}
