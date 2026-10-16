/**
 * "How pictures are made" — slice 5 of the owner-approved Settings redesign
 * (`docs/design/settings-redesign.md`, section 5).
 *
 * Four cards over the four hands-off picture choices — outlier removal,
 * drizzle, the mosaic border trim and calibration — each saying in plain words
 * what a hands-off stack will **actually** do with today's settings, above the
 * full stacking-defaults list (folded behind "Show all stacking options").
 * This module is the copy and the arithmetic, free of React so every answer is
 * pinned as a value; `PicturesMade.tsx` draws it.
 *
 * **Every value was checked against the code that acts on it**, and two of the
 * mockup's did not survive:
 *
 * - The mockup's calibration card reads *"Ask me"*. Nothing asks:
 *   `Settings.auto_bind_calibration` is a plain switch, and off means a
 *   hands-off stack is made with exactly the masters its target (or the global
 *   defaults) name — usually none (`pipeline._auto_bind_calibration`). So the
 *   off value says that.
 * - The mockup shows outlier removal and drizzle as "Automatic" unconditionally.
 *   Both are automatic only while the **global stacking defaults** below the
 *   cards express no choice: `walkaway.apply_unattended_rejection` stands
 *   aside for any saved `auto_reject` / `sigma_clip` / `min_max_reject` (unless
 *   `auto_reject_on_unattended` overrides it), and `walkaway.apply_auto_drizzle`
 *   stands aside for any saved `drizzle`, on *or* off. A card that said
 *   "Automatic" over a saved choice would be the page contradicting itself one
 *   scroll down, so each card reads the defaults too and says which one wins.
 *
 * A target's own "Save as defaults" can still name a method or drizzle for that
 * one target; the section's intro says so rather than every card repeating it.
 */

export type SettingsForm = Record<string, unknown>;
export type SettingsPatch = Record<string, unknown>;

/** The rejection keys whose mere *presence* is a choice (`walkaway.AUTO_REJECT_OPT_KEYS`). */
export const REJECT_KEYS = ["auto_reject", "sigma_clip", "min_max_reject"] as const;

export type PictureCardId = "outliers" | "drizzle" | "trim" | "calibration";

export interface PictureCardState {
  id: PictureCardId;
  title: string;
  desc: string;
  /** The `Settings` field this card's switch writes. */
  field: string;
  /** The switch's own label (in plain words). */
  switchLabel: string;
  checked: boolean;
  /** The short "what happens now" value, shown as a pill. */
  value: string;
  /** One sentence on what the value means for the next hands-off stack. */
  note: string;
  /**
   * When a saved stacking default overrules the switch: why, and the patch
   * that hands the choice back to AstroStack (a preview until Save, like
   * every other control here).
   */
  overruled: { text: string; button: string; patch: SettingsPatch } | null;
  was: string;
}

function stackDefaults(form: SettingsForm): Record<string, unknown> {
  const d = form.default_stack_options;
  return d && typeof d === "object" && !Array.isArray(d) ? (d as Record<string, unknown>) : {};
}

/** `default_stack_options` with `keys` removed — the "let AstroStack decide" patch. */
function withoutDefaults(form: SettingsForm, keys: readonly string[]): SettingsPatch {
  const next = { ...stackDefaults(form) };
  for (const k of keys) delete next[k];
  return { default_stack_options: next };
}

/** The rejection method the global defaults name, in plain words, or null. */
export function savedRejection(form: SettingsForm): string | null {
  const d = stackDefaults(form);
  if (!REJECT_KEYS.some((k) => k in d)) return null;
  // Same precedence as the engine: auto_reject overrides the two toggles, and
  // min/max takes precedence over κ-σ (`stacker._resolve_auto_reject`,
  // `combine_method`). An absent `sigma_clip` is `StackOptions`' own default,
  // which is **on** — so a saved `auto_reject: false` alone still clips.
  if (d.auto_reject) return "automatic";
  if (d.min_max_reject) return "drop the brightest and darkest";
  if (("sigma_clip" in d) ? d.sigma_clip : true) return "drop the odd ones out";
  return "none";
}

export function outliersCard(form: SettingsForm): PictureCardState {
  const override = Boolean(form.auto_reject_on_unattended);
  const saved = savedRejection(form);
  const automatic = saved === null || saved === "automatic" || override;
  let value: string;
  let note: string;
  if (automatic) {
    value = "Automatic";
    note = saved !== null && saved !== "automatic"
      ? "AstroStack picks the method on every hands-off stack, even over the one saved in "
        + "your stacking defaults below."
      : "On a few frames it drops the brightest and darkest value at each spot; on many, "
        + "whatever stands out from the rest — so a lone satellite trail is caught even on a thin "
        + "night.";
  } else if (saved === "none") {
    value = "Off — your stacking defaults";
    note = "Your stacking defaults below turn outlier removal off, so trails and hot "
      + "pixels that reach a hands-off stack stay in the picture.";
  } else {
    value = `Your choice: ${saved}`;
    // κ-σ only bites from ~11 frames (`kappa_min_frames`); min/max works on a
    // thin stack, so only the first earns the caveat.
    note = saved === "drop the odd ones out"
      ? "Your stacking defaults below name a method, so every hands-off stack uses it — "
        + "even on a thin night, where it can miss a lone satellite trail."
      : "Your stacking defaults below name a method, so every hands-off stack uses it.";
  }
  return {
    id: "outliers",
    title: "Remove satellites & hot pixels",
    desc: "Compares every frame and drops the odd one out at each spot.",
    field: "auto_reject_on_unattended",
    switchLabel: "Choose for me even when a method is saved",
    checked: override,
    value,
    note,
    overruled: null,
    was: "Sigma clipping / outlier rejection",
  };
}

export function drizzleCard(form: SettingsForm): PictureCardState {
  const on = form.auto_drizzle !== false;
  const d = stackDefaults(form);
  const saved = "drizzle" in d;
  let value: string;
  let note: string;
  if (saved) {
    value = d.drizzle ? "Always — your stacking defaults" : "Never — your stacking defaults";
    note = d.drizzle
      ? "Your stacking defaults below turn drizzle on, so every hands-off stack is drizzled, "
        + "deep or not."
      : "Your stacking defaults below turn drizzle off, so no hands-off stack is drizzled.";
  } else if (on) {
    value = "Automatic when it pays off";
    note = "Only on a deep target — about 200 frames on each patch of sky — whose frames moved "
      + "slightly between shots, and only if it fits in memory. Each picture's History says "
      + "which it was.";
  } else {
    value = "Off";
    note = "Hands-off stacks are made at the camera's own size.";
  }
  return {
    id: "drizzle",
    title: "Sharper, bigger picture",
    desc: "On deep targets, builds a finer image from the tiny shifts between frames.",
    field: "auto_drizzle",
    switchLabel: "Let AstroStack decide",
    checked: on,
    value,
    note,
    overruled: saved
      ? {
        text: "While your stacking defaults name drizzle, this switch has no effect.",
        button: "Let AstroStack decide instead",
        patch: { ...withoutDefaults(form, ["drizzle"]), auto_drizzle: true },
      }
      : null,
    was: "Drizzle, drizzle scale, pixfrac",
  };
}

export function trimCard(form: SettingsForm): PictureCardState {
  const on = form.auto_crop_border !== false;
  return {
    id: "trim",
    title: "Trim ragged mosaic edges",
    desc: "When Auto finishes a mosaic, cuts off the uneven border it leaves.",
    field: "auto_crop_border",
    switchLabel: "Trim the border",
    checked: on,
    value: on ? "On" : "Off",
    note: on
      ? "Only the ragged edge goes; the editor's Trim border button can still re-crop by hand."
      : "Auto keeps the whole frame exactly as stacked; you can still trim by hand in the editor.",
    overruled: null,
    was: "Let Auto trim the ragged border off a mosaic",
  };
}

export function calibrationCard(form: SettingsForm): PictureCardState {
  const on = Boolean(form.auto_bind_calibration);
  return {
    id: "calibration",
    title: "Use my darks and flats",
    desc: "Applies matching calibration frames you've added to the library.",
    field: "auto_bind_calibration",
    switchLabel: "Use matching ones automatically",
    checked: on,
    value: on ? "Automatic" : "Only when I pick them",
    note: on
      ? "A hands-off stack with none chosen uses the library's masters that confidently match "
        + "its frames' exposure, gain and size. No confident match, no calibration."
      : "A hands-off stack uses only the masters its target's own saved defaults name — "
        + "usually none.",
    overruled: null,
    was: "Auto-apply matching calibration masters to hands-off stacks",
  };
}

export function pictureCards(form: SettingsForm): PictureCardState[] {
  return [outliersCard(form), drizzleCard(form), trimCard(form), calibrationCard(form)];
}

/** Every `Settings` field the four cards write, for the drift test. */
export const PICTURE_CARD_FIELDS = [
  "auto_reject_on_unattended", "auto_drizzle", "auto_crop_border", "auto_bind_calibration",
  "default_stack_options",
] as const;
