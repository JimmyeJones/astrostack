import type { EditOp, StackOptionField } from "../../api/client";

/**
 * The values an op *starts at* when someone adds it from the editor — and what
 * its Reset buttons return to — where that differs from the engine schema's own
 * default.
 *
 * **Why the Stretch is here.** The engine's `tone.stretch` schema defaults to the
 * manual asinh curve at black point 0.35, and that black point sits just *above*
 * the sky median by construction (`asinh_stretch`: 0.33 is the median), so on any
 * picture it clips about half the sky to pure black. Meanwhile an editor with no
 * Stretch shows the pipeline's STF auto-stretch (sky at 20 % grey). So "Add
 * Stretch" — and the "No stretch" nudge's own button — swapped the look a
 * beginner was judging for a crushed, half-black sky (measured: median sky 0.20 →
 * 0.00, 0.04 % → 54 % of covered pixels at exactly 0). Starting the added op in
 * STF at the schema's own sky level makes adding it a no-op on screen: the same
 * picture, now with a control. Asinh is one click away in the op's Curve menu,
 * with its own measured "Auto stretch" button.
 *
 * Frontend-only on purpose: the schema default is what the engine fills into a
 * saved recipe that lacks the key, so changing *it* could move a picture already
 * on disk. Every saved recipe carries its mode explicitly, and this never reads
 * one — it only seeds a new op.
 */
export const ADDED_OP_DEFAULTS: Record<string, Record<string, unknown>> = {
  "tone.stretch": { mode: "stf" },
};

/** The starting value of one of `spec`'s params (see {@link ADDED_OP_DEFAULTS}). */
export function paramStartValue(spec: EditOp, p: StackOptionField): unknown {
  const over = ADDED_OP_DEFAULTS[spec.id];
  if (over && Object.prototype.hasOwnProperty.call(over, p.key)
      && (p.options == null || p.options.includes(over[p.key] as string))) {
    return over[p.key];
  }
  return p.default;
}

/** Every param of `spec` at its starting value — a freshly added op's params. */
export function opStartParams(spec: EditOp): Record<string, unknown> {
  const params: Record<string, unknown> = {};
  spec.params.forEach((p) => { params[p.key] = paramStartValue(spec, p); });
  return params;
}
