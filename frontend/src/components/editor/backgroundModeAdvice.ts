import type { EditOp, ObjectInfo } from "../../api/client";

/** The editor ops whose "Mode" param chooses between fitting the sky separately
 * in R/G/B and fitting one shared shape, mapped to what that op's model is
 * called in its own help text. Both carry the identical hazard on a big emission
 * nebula, and both offer the identical `luminance` escape. */
const MODE_OPS: Record<string, string> = {
  "background.subtract": "sky model",
  "background.final_gradient": "gradient model",
};

/** "This nebula needs the shared sky fit" — the editor's version of the Stack
 * form's background-mode nudge.
 *
 * The *fact* comes from the server: `seestack.bg_advice.background_mode_hint`
 * decides, from the bundled offline catalog alone, whether this target is
 * extended emission and big enough that a per-channel fit will bend into it by a
 * different amount in each colour. Its presence (and its `mode`) is all this
 * helper reads — deliberately **not** its `text`, which is written for the Stack
 * form and describes the *per-frame* flatten that runs over each sub. Here the
 * image is already stacked and that pass has been and gone, so the sentence has
 * to be about this op's own fit or it would mislead.
 *
 * Silent when: the op isn't one of the two with a Mode param; the target matched
 * no catalog entry, or isn't one of the few the advice covers; or the op is
 * already on the advised mode (which is `background.final_gradient`'s default,
 * so that op only ever speaks up after someone switched it away). Advisory only —
 * nothing changes until the button is pressed, and no op default moves.
 */
export function backgroundModeAdvice(
  info: ObjectInfo | null | undefined,
  spec: EditOp | null | undefined,
  params: Record<string, unknown> | null | undefined,
): { mode: string; text: string } | null {
  if (!spec) return null;
  const model = MODE_OPS[spec.id];
  if (!model) return null;
  const hint = info?.background_mode_hint;
  if (!hint || !hint.mode) return null;
  // Resolve the mode the op is *actually* running at: an op instance carries a
  // param only once it's been set, so an untouched op falls back to the schema
  // default (per_channel for subtract, luminance for gradient removal).
  const fallback = spec.params.find((p) => p.key === "mode")?.default;
  const current = String(params?.mode ?? fallback ?? "").trim();
  if (!current || current === hint.mode) return null;
  return {
    mode: hint.mode,
    text:
      "This target is a large patch of glowing gas, and it looks different in "
      + `red, green and blue. Fitting a separate ${model} for each colour bends `
      + "each one into the nebula by a different amount, which can leave cyan "
      + `cores and red halos. Luminance fits one shared ${model} and subtracts `
      + "it equally from all three, so the nebula keeps its colour.",
  };
}

/** The advised mode's human label, read off the op's own schema so the button
 * can't drift from the control it changes ("luminance" → "Luminance"). Falls
 * back to the raw value when the schema carries no label for it. */
export function backgroundModeOptionLabel(
  mode: string,
  spec: EditOp | null | undefined,
): string {
  const field = spec?.params.find((p) => p.key === "mode");
  return field?.option_labels?.[mode] ?? mode;
}
