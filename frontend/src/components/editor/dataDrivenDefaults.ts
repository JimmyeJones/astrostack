import type { OpInstance } from "../../api/client";

/** A data-driven default for one op: which param it sets and the value measured
 * from the target's data (the same values the per-op "From your data" buttons
 * offer). */
export type OpSuggestion = { param: string; value: number };

/** Return a new pipeline with each present op's data-driven param seeded from its
 * suggestion. Ops with no suggestion (or already at the suggested value) are left
 * untouched; the input array and its op objects are never mutated. */
export function applyDataDrivenDefaults(
  ops: OpInstance[],
  suggestions: Record<string, OpSuggestion>,
): OpInstance[] {
  return ops.map((o) => {
    const s = suggestions[o.id];
    if (!s || o.params[s.param] === s.value) return o;
    return { ...o, params: { ...o.params, [s.param]: s.value } };
  });
}

/** How many present ops would actually change if the defaults were applied —
 * drives whether the "Use data defaults" toolbar button is shown and its count. */
export function countDataDrivenDefaults(
  ops: OpInstance[],
  suggestions: Record<string, OpSuggestion>,
): number {
  let n = 0;
  for (const o of ops) {
    const s = suggestions[o.id];
    if (s && o.params[s.param] !== s.value) n += 1;
  }
  return n;
}
