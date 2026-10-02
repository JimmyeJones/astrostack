import type { EditOp, OpInstance } from "../../api/client";
import { geometryOpReshapesFrame } from "./cropDrag";

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

/** The uids of every *enabled* Coverage-leveling op that an upstream geometry op
 * has left doing **nothing**.
 *
 * The op levels the sky per coverage *level*, which it can only do by binning the
 * image against the run's own coverage map — a map captured at the stack
 * canvas's geometry. `_level_coverage` (`seestack/edit/ops/background.py`)
 * therefore carries a shape guard: if an earlier op has already reshaped the
 * frame, the two can no longer be aligned and it returns the image untouched,
 * "skip rather than crash the whole render". Measured on a four-panel canvas with
 * a real sky step between the panels: leveling on its own moves the picture by
 * 0.142 of full scale, and with an aimed Crop, Rotate or Resize above it by
 * **0.000000** — the control is dead, and nothing said so.
 *
 * That silence is the gap, not the skip. This op already tells the reader when it
 * can do nothing for the *other* reason — a single-field stack has no panels to
 * equalise — on the grounds that it is better to say so "rather than let the
 * control silently do nothing". This is the same sentence owed for the second
 * reason, and the editor's existing "this op is doing nothing, here is why and
 * one click to fix it" family (`stageConflicts.ts`) is structurally blind to it:
 * `stageConflicts` returns nothing at all when no stretch op is enabled, which is
 * exactly when a geometry op can sit above a linear pass without any other
 * surface remarking on it.
 *
 * **A geometry op at its own defaults is not one of these.** All three default to
 * a no-op, so a Crop, Rotate or Resize fresh from the Add menu leaves the frame's
 * shape alone and the leveling still runs (measured: 0.142 either way).
 * {@link geometryOpReshapesFrame} is the question — the same predicate
 * `reshapes_frame` answers in the engine — so this can only ever name an op that
 * really is dead. Pure.
 */
export function strandedCoverageLevelingUids(ops: OpInstance[]): string[] {
  const out: string[] = [];
  let reshaped = false;
  for (const op of ops) {
    if (!op.enabled) continue;
    if (op.id.startsWith("geometry.")) reshaped = reshaped || geometryOpReshapesFrame(op);
    else if (reshaped && op.id === LEVEL_COVERAGE_ID) out.push(op.uid);
  }
  return out;
}

/** `ops` with the named Coverage-leveling ops moved to the **front**, in the
 * order they already appear — the one-click fix for
 * {@link strandedCoverageLevelingUids}.
 *
 * The front is this op's canonical home rather than merely somewhere earlier:
 * it is where {@link prependCoverageLeveling} puts it when a preset is applied to
 * a mosaic, and where the one-click Auto recipe builds it. Moving it there clears
 * the stranding whatever put the geometry op above it, and leaves every other
 * op's relative order alone. Pure and non-mutating; returns the input unchanged
 * when `uids` is empty.
 */
export function moveCoverageLevelingToFront(
  ops: OpInstance[], uids: string[],
): OpInstance[] {
  if (!uids.length) return ops;
  const moved = ops.filter((o) => uids.includes(o.uid));
  if (!moved.length) return ops;
  return [...moved, ...ops.filter((o) => !uids.includes(o.uid))];
}
