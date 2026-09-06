import type { PinnedStackOption, StackOptionField } from "./api/client";

/** "This target ignores some of your global settings" — the Stack-form note.
 *
 * `Save as defaults` persists the **whole** form, not the handful of things the
 * user changed, and a target's saved blob then wins over the global
 * `default_stack_options` in both readers (this form's seed and the hands-off
 * auto-stack). So a switch flipped globally months later silently never reaches
 * a target that once pressed Save — with nothing on any screen saying so. The
 * server does the comparing (`GET .../stack-defaults/pinned`, which measures
 * against the exact seed this form would have been given); these helpers only
 * decide how to say it, and how to hand the form the global values back.
 */

/** One option value, as the control on this form would show it.
 *
 * Reads the engine's own descriptors so the note can't drift from the control
 * it names: an enum prints its `option_labels` caption, a checkbox prints
 * on/off rather than `true`/`false`, and anything the schema doesn't cover
 * falls back to the plain value.
 */
export function pinnedValueText(
  value: unknown,
  field: StackOptionField | undefined,
): string {
  if (typeof value === "boolean") return value ? "on" : "off";
  if (value === null || value === undefined) return "not set";
  const raw = String(value);
  if (field?.type === "enum") return field.option_labels?.[raw] ?? raw;
  return raw;
}

/** The one-line summary, or `null` when there is nothing to say.
 *
 * Deliberately silent for a target that saved defaults which still *agree* with
 * the global ones — pressing Save is not itself worth a warning, and a note that
 * appears for everybody is a note nobody reads.
 */
export function pinnedSummary(pinned: PinnedStackOption[] | undefined): string | null {
  const n = pinned?.length ?? 0;
  if (n === 0) return null;
  return n === 1
    ? "1 saved setting on this target is different from your global default"
    : `${n} saved settings on this target are different from your global defaults`;
}

/** "Auto outlier removal: off here, on globally" — one line per pinned option. */
export function pinnedLine(
  option: PinnedStackOption,
  fields: StackOptionField[] | undefined,
): string {
  const field = (fields ?? []).find((f) => f.key === option.key);
  const here = pinnedValueText(option.saved, field);
  const global = pinnedValueText(option.global_value, field);
  return `${option.label}: ${here} here, ${global} globally`;
}

/** The form patch that adopts every global value at once.
 *
 * One `setValues` update rather than a click per row: the estimate query is
 * keyed on several of these, so applying them one at a time would re-query
 * through a string of intermediate states. Nothing is saved by this — the user
 * still has to press **Save as defaults**, which is what makes the change
 * reviewable before it reaches the unattended stack.
 */
export function adoptGlobalsPatch(
  pinned: PinnedStackOption[] | undefined,
): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  for (const p of pinned ?? []) patch[p.key] = p.global_value;
  return patch;
}
