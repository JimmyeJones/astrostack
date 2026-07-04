import type { OpInstance } from "../../api/client";
import { matchesSuggestion } from "./suggestionMatch";

/** A data-driven default for one op: which param it sets, the value measured from
 * the target's data (the same values the per-op "From your data" buttons offer),
 * and the control's step so "already set" is judged with the *same* half-step
 * tolerance the per-param button uses. */
export type OpSuggestion = { param: string; value: number; step?: number | null };

/** True when this op should be re-seeded from its suggestion: it is enabled, has a
 * suggestion, and isn't already sitting at the suggested value (within the
 * control's half-step tolerance — matching the per-param "✓ already set"
 * indicator, so the toolbar and the buttons never disagree). Disabled ops are
 * skipped: they have no effect and aren't shown as tunable. */
function wouldChange(o: OpInstance, s: OpSuggestion | undefined): s is OpSuggestion {
  return !!s && o.enabled !== false
    && !matchesSuggestion(o.params[s.param], s.value, s.step);
}

/** Return a new pipeline with each present op's data-driven param seeded from its
 * suggestion. Ops with no suggestion, disabled ops, or ops already at the
 * suggested value (within tolerance) are left untouched; the input array and its
 * op objects are never mutated. */
export function applyDataDrivenDefaults(
  ops: OpInstance[],
  suggestions: Record<string, OpSuggestion>,
): OpInstance[] {
  return ops.map((o) => {
    const s = suggestions[o.id];
    if (!wouldChange(o, s)) return o;
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
    if (wouldChange(o, suggestions[o.id])) n += 1;
  }
  return n;
}
