import type { ObjectInfo, StackOptionField } from "./api/client";

/** "Your target needs a different background-flatten mode" — the Stack-form nudge.
 *
 * The advice itself is decided server-side from the bundled offline catalog
 * (`seestack.bg_advice.background_mode_hint`: extended-emission type + a size
 * big enough for the default per-channel sky fit to bend into it), so the
 * thresholds and the wording live in exactly one place. This helper only decides
 * whether the suggestion is worth *showing* against the form's current values.
 *
 * Silent when: the target matched no catalog entry or isn't one of the few the
 * advice covers; the per-frame flatten is switched off entirely (its mode then
 * changes nothing); or the form is already on the advised mode — whether the
 * user chose it, "Reuse settings" carried it over, or they already clicked this
 * nudge. Advisory only: nothing is applied until the button is pressed, and
 * per-channel stays the default.
 */
export function backgroundModeNudge(
  info: ObjectInfo | null | undefined,
  values: Record<string, unknown>,
): { mode: string; text: string } | null {
  const hint = info?.background_mode_hint;
  if (!hint || !hint.mode || !hint.text) return null;
  if (!values.background_flatten) return null;
  if (String(values.background_mode ?? "") === hint.mode) return null;
  return { mode: hint.mode, text: hint.text };
}

/** The mode's human label, read off the engine's own option labels so the button
 * can't drift from the control it changes ("luminance" → "Luminance"). Falls
 * back to the raw value when the schema doesn't carry a label for it. */
export function backgroundModeLabel(
  mode: string,
  fields: StackOptionField[] | undefined,
): string {
  const field = (fields ?? []).find((f) => f.key === "background_mode");
  return field?.option_labels?.[mode] ?? mode;
}
