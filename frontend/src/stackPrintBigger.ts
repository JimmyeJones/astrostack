// Turns the estimate's `print_plan.bigger_*` into a one-click action for the
// Stack form — the sibling of `stackMemoryFix.ts`, and deliberately the same
// shape.
//
// The panel already says "Turning Drizzle on at ×1.3 would print it at A3
// instead", and the engine *verified* that scale (it stepped the 0.1 grid until
// the canvas really qualified for the paper, and dropped the offer entirely if
// the result would bust the memory budget). But the two knobs the sentence names
// live inside the form's collapsed **advanced** disclosure, so a beginner who
// reads it still has to go hunting. Naming a number the form could just set is
// the friction; this is the button that sets it.
//
// Kept pure and separate so the label and the "is there anything to offer?"
// rule are unit-testable without rendering the form.

export interface PrintPlanInfo {
  bigger_name?: string | null;
  bigger_drizzle_scale?: number | null;
}

export interface PrintBiggerAction {
  /** Button text: the lever and the paper it reaches. */
  label: string;
  /** The StackOptions keys to set, **together** — the estimate query is keyed on
   *  both, so they must land in one state update or the panel re-queries twice
   *  and flickers between two verdicts on the way. */
  values: Record<string, unknown>;
}

/** `%g`-style, so ×1.5 and ×2 read the way the engine's own sentence writes them. */
function formatScale(scale: number): string {
  const rounded = Number(scale.toFixed(2));
  return rounded % 1 === 0 ? rounded.toFixed(0) : String(rounded);
}

/**
 * The one-click "print it bigger" action, or null when there is nothing honest
 * to offer.
 *
 * `current` is the form's own drizzle state, used only to refuse a button that
 * would change nothing. The engine already steps *up* from whatever is set, so
 * this should never fire — it is here because a control that appears to do
 * something and does nothing is exactly the defect this button was added to fix.
 */
export function printBiggerAction(
  plan: PrintPlanInfo | null | undefined,
  current: { drizzle: boolean; scale: number },
): PrintBiggerAction | null {
  if (!plan) return null;
  const scale = plan.bigger_drizzle_scale;
  const name = (plan.bigger_name ?? "").trim();
  if (scale == null || !Number.isFinite(scale) || scale <= 0 || !name) return null;
  if (current.drizzle && Math.abs(current.scale - scale) < 1e-9) return null;
  return {
    label: `Use drizzle ×${formatScale(scale)} — prints at ${name}`,
    values: { drizzle: true, drizzle_scale: scale },
  };
}
