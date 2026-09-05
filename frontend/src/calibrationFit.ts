/** Does a calibration master actually fit this target's frames?
 *
 * The exposure/temperature cautions on the Stack form are advisories — a
 * mismatched dark still calibrates, just imperfectly. A **size** mismatch is
 * different in kind: `CalibrationMasters.validate` refuses a master whose
 * dimensions differ from the frames, so picking a master built for another
 * camera (or another binning mode) doesn't produce a worse picture — it kills the
 * whole stack with an error a beginner can't decode. And on the walk-away
 * auto-stack path such a master is silently skipped, so "I added darks" quietly
 * isn't true. Both cases deserve saying out loud, at pick time.
 *
 * Pure/no-React so the wording and the "can't tell" cases stay unit-testable.
 */

/** The master fields this check needs (a subset of the masters payload). */
export interface MasterDims {
  name?: string;
  width_px?: number | null;
  height_px?: number | null;
  bayer_pattern?: string | null;
}

/** The target's frame size, as reported by `calibration-suggestions.params`. */
export interface FrameDims {
  width_px?: number | null;
  height_px?: number | null;
  bayer_pattern?: string | null;
}

/** The four real 2×2 colour-filter phases. Anything else — a blank card, a mono
 * master, an older backend's missing field — reads as *undeclared*, so the check
 * below can only ever fire on a positive conflict. Mirrors the engine's
 * `_norm_bayer`. */
const CFA_PHASES = ["RGGB", "BGGR", "GRBG", "GBRG"];

function normBayer(pattern: string | null | undefined): string | null {
  if (!pattern) return null;
  const p = String(pattern).trim().toUpperCase();
  return CFA_PHASES.includes(p) ? p : null;
}

/** True when the master's colour-filter phase and the subs' are both known and
 * differ — the same one-sided rule as `masterFitsFrames`. */
export function bayerConflicts(
  master: MasterDims | null | undefined,
  frames: FrameDims | null | undefined,
): boolean {
  const mine = normBayer(master?.bayer_pattern);
  const theirs = normBayer(frames?.bayer_pattern);
  return mine !== null && theirs !== null && mine !== theirs;
}

/** The plain-language warning for a chosen **flat** built on another colour-filter
 * phase, or null when it matches (or we can't tell).
 *
 * Flats only, and that asymmetry is the point: a flat divides into the raw Bayer
 * mosaic *per colour*, so one phase out corrects every red photosite with a green
 * value — the picture keeps its detail and comes out the wrong colour on every
 * frame. `CalibrationMasters.validate` therefore refuses it outright, exactly as
 * it refuses a wrong *size*, which is why this reads as a blocker rather than an
 * advisory. A dark or bias corrects each physical pixel, so its phase changes
 * nothing and it is never flagged here. */
export function flatBayerWarning(
  flat: MasterDims | null | undefined,
  frames: FrameDims | null | undefined,
): string | null {
  if (!flat || !bayerConflicts(flat, frames)) return null;
  return (
    `This flat was built on a ${normBayer(flat.bayer_pattern)} colour-filter ` +
    `layout, but this target's frames are ${normBayer(frames?.bayer_pattern)} — ` +
    `a different camera or readout mode, so dividing by it would swap the colour ` +
    `channels and tint every frame. Stacking with it will fail; pick a matching ` +
    `flat or leave this blank.`
  );
}

/** True when the master's size and the subs' size are both known and differ.
 *
 * Deliberately one-sided: an older master (or a target whose frames never
 * recorded a size) can't be *disproved*, so it is never flagged. This mirrors the
 * server-side gate on the walk-away path, which also only refuses on a positive
 * conflict. */
export function masterFitsFrames(
  master: MasterDims | null | undefined,
  frames: FrameDims | null | undefined,
): boolean {
  if (!master || !frames) return true;
  const { width_px: mw, height_px: mh } = master;
  const { width_px: fw, height_px: fh } = frames;
  if (mw == null || mh == null || fw == null || fh == null) return true;
  return mw === fw && mh === fh;
}

/** The plain-language warning for a chosen master that can't apply to these
 * frames, or null when it fits (or we can't tell). `kind` is the user-facing
 * word for the slot ("dark", "flat", "flat-dark", "bias"). */
export function masterSizeWarning(
  kind: string,
  master: MasterDims | null | undefined,
  frames: FrameDims | null | undefined,
): string | null {
  if (!master || masterFitsFrames(master, frames)) return null;
  return (
    `This ${kind} is ${master.width_px}×${master.height_px}, but this target's ` +
    `frames are ${frames?.width_px}×${frames?.height_px} — it was built for a ` +
    `different camera or binning mode, so it can't be applied. Stacking with it ` +
    `will fail; pick a matching master or leave this blank.`
  );
}

/** Suffix for a master's entry in the picker, so a mismatched one reads as
 * unusable *before* it's chosen. Empty string when it fits (or we can't tell). */
export function masterOptionSuffix(
  master: MasterDims | null | undefined,
  frames: FrameDims | null | undefined,
  kind?: string,
): string {
  if (!masterFitsFrames(master, frames)) return " — wrong size for this target";
  // Flats only: a dark/bias on another phase is still perfectly usable (see
  // `flatBayerWarning`), so badging it unusable would be a lie.
  if (kind === "flat" && bayerConflicts(master, frames)) {
    return " — wrong colour filter for this target";
  }
  return "";
}

/** The bias slot's own size warning — which is *not* the generic one.
 *
 * A master bias is subtracted from the lights only when **no** master dark is
 * chosen (a dark already carries the bias pedestal), and the engine's
 * `CalibrationMasters.validate` mirrors that: it only refuses a wrong-sized bias
 * on that path. So "stacking with it will fail" — true of every other slot — is
 * simply false once a dark is picked: there the bias is never applied to the
 * lights at all, and what its size does decide is whether it can scale the dark
 * (see `darkScalingBlockedNote`). Saying the wrong one of those two things is
 * worse than saying nothing, so with a dark present this stays silent and lets
 * the scaling note speak. */
export function biasSizeWarning(
  bias: MasterDims | null | undefined,
  frames: FrameDims | null | undefined,
  dark: MasterDims | null | undefined,
): string | null {
  if (dark) return null;
  return masterSizeWarning("bias", bias, frames);
}

/** The flat-dark slot's own size warning — also *not* the generic one.
 *
 * Same shape as `biasSizeWarning`, for the same reason: the shared
 * "stacking with it will fail" line is untrue here. `CalibrationMasters.validate`
 * never looks at the flat-dark, and `CalibrationMasters.load` compares it to the
 * **flat** (not to the frames) and, on a mismatch, just skips the subtraction and
 * carries on. So the stack succeeds — it simply produces a *worse* flat, one
 * normalised with its own dark-current + bias pedestal still in it, which
 * flattens the flat's contrast and leaves part of the vignetting uncorrected on
 * every frame. Telling the beginner their stack will fail sends them off to fix
 * something that isn't broken and hides the thing that is.
 *
 * Compared against the flat, which is the engine's actual test — and one-sided
 * like the rest of this module, so a master or a flat that never recorded a size
 * is never flagged. */
export function flatDarkSizeWarning(
  flatDark: MasterDims | null | undefined,
  flat: MasterDims | null | undefined,
): string | null {
  if (!flatDark || !flat) return null;
  if (masterFitsFrames(flatDark, flat as FrameDims)) return null;
  return (
    `This flat-dark is ${flatDark.width_px}×${flatDark.height_px} but your flat ` +
    `is ${flat.width_px}×${flat.height_px} — it was built for a different camera ` +
    `or binning mode, so it can't be subtracted from the flat. Stacking still ` +
    `works, but your flat keeps its own dark pedestal, so vignetting is ` +
    `corrected less accurately. Pick a flat-dark that matches the flat, or leave ` +
    `this blank.`
  );
}

/** Which calibration fields the Stack form should write when the **Master flat**
 * pick changes.
 *
 * Clearing the flat must clear the flat-dark with it. A flat-dark is subtracted
 * *from the flat*, so `CalibrationMasters.load` only ever loads one inside its
 * `if flat_path:` branch — with no flat the pick is submitted and silently
 * ignored. And the form hides the flat-dark picker (and both its warnings) once
 * the flat is gone, so nothing on screen would say the stale pick was still
 * there. */
export function flatPickPatch(
  flatId: string | null,
): { flat_master_id: string | null; flat_dark_master_id?: null } {
  return flatId
    ? { flat_master_id: flatId }
    : { flat_master_id: null, flat_dark_master_id: null };
}

/** Can this bias actually hold the readout pedestal fixed while the dark is
 * rescaled? Mirrors the engine's `_dark_scaling_applies` shape test.
 *
 * One-sided like the rest of this module: a master that never recorded a size
 * can't be *disproved*, so it is assumed to fit. */
export function biasCanScaleDark(
  bias: MasterDims | null | undefined,
  dark: MasterDims | null | undefined,
): boolean {
  return masterFitsFrames(bias, dark as FrameDims | null | undefined);
}

/** Why turning dark exposure-scaling on changed nothing, or null when it works
 * (or there is no scaling to do).
 *
 * The engine scales `dark = bias + (dark − bias)·(t_sub / t_dark)`, which needs
 * the bias and the dark to be the same size; when they aren't it quietly
 * subtracts the dark **unscaled**. Without this the form went the other way and
 * said "Dark exposure-scaling is on — this 30s dark will be scaled to match your
 * 10s subs", which is a promise the stack doesn't keep. */
export function darkScalingBlockedNote(
  dark: MasterDims | null | undefined,
  bias: MasterDims | null | undefined,
): string | null {
  if (!dark || !bias || biasCanScaleDark(bias, dark)) return null;
  return (
    `Dark exposure-scaling is on, but this bias is ${bias.width_px}×` +
    `${bias.height_px} and the dark is ${dark.width_px}×${dark.height_px} — ` +
    `scaling holds the bias pedestal fixed while the dark current is rescaled, ` +
    `so both must be the same size. The dark will be subtracted unscaled. Use a ` +
    `bias built from the same camera and binning as the dark.`
  );
}


/* --- "is this master a poor match?" — one predicate, shared with the engine ---
 *
 * The Stack form warns about an exposure/temperature mismatch at *pick* time; the
 * engine's `CalibrationMasters.calibration_warnings` reports the same two
 * mismatches on the finished run. Each side used to choose its own threshold —
 * and the form's was both looser *and* measured against a different denominator
 * (the subs' exposure, not the master's) — so on a borderline pair the app could
 * stay quiet before the night was spent and complain about it afterwards. A 30 s
 * dark on 25 s subs was exactly that: silent at pick time, flagged on the run.
 *
 * These mirror the engine constants and are the *fallback*: the Stack form prefers
 * the values `…/calibration-suggestions` serves in `tolerances`, so the engine
 * stays the single source of truth and an older backend still behaves sensibly.
 */

/** Fallback for the engine's `EXPOSURE_MISMATCH_TOL` (fraction of the master's
 *  own exposure). */
export const EXPOSURE_MISMATCH_TOL = 0.15;
/** Fallback for the engine's `TEMP_MISMATCH_TOL_C` (degrees C). */
export const TEMP_MISMATCH_TOL_C = 5;

/** Optional `tolerances` block from the calibration-suggestions payload. */
export interface MismatchTolerances {
  exposure_frac?: number | null;
  temp_c?: number | null;
}

/** A usable positive threshold from the server, or the built-in fallback. */
function tol(served: number | null | undefined, fallback: number): number {
  return typeof served === "number" && Number.isFinite(served) && served > 0
    ? served
    : fallback;
}

/** True when a master's exposure differs enough from the frames it would
 *  calibrate to be worth warning about — the engine's own test,
 *  `|t_frames / t_master − 1| > tolerance`.
 *
 *  One-sided like the size check: an unknown or non-positive exposure on either
 *  side can't be disproved, so it never warns. */
export function exposureMismatch(
  masterExposureS: number | null | undefined,
  frameExposureS: number | null | undefined,
  tolerances?: MismatchTolerances | null,
): boolean {
  if (masterExposureS == null || frameExposureS == null) return false;
  if (!(masterExposureS > 0) || !(frameExposureS > 0)) return false;
  const limit = tol(tolerances?.exposure_frac, EXPOSURE_MISMATCH_TOL);
  return Math.abs(frameExposureS / masterExposureS - 1) > limit;
}

/** True when a master's sensor temperature is far enough from the frames' to be
 *  worth warning about (`>=` the tolerance, mirroring the engine). */
export function tempMismatch(
  masterTempC: number | null | undefined,
  frameTempC: number | null | undefined,
  tolerances?: MismatchTolerances | null,
): boolean {
  if (masterTempC == null || frameTempC == null) return false;
  if (!Number.isFinite(masterTempC) || !Number.isFinite(frameTempC)) return false;
  return Math.abs(masterTempC - frameTempC) >= tol(tolerances?.temp_c, TEMP_MISMATCH_TOL_C);
}

// --- Which masters the form should recommend -------------------------------

/** The suggestion fields the recommendation needs (a subset of
 *  `CalibrationSuggestions`, so this stays testable on plain objects). */
export interface MasterSuggestion {
  dark_master_id?: number | null;
  flat_master_id?: number | null;
  flat_dark_master_id?: number | null;
  bias_master_id?: number | null;
  confident?: {
    dark_master_id?: number | null;
    flat_master_id?: number | null;
    flat_dark_master_id?: number | null;
    bias_master_id?: number | null;
    scale_dark_to_light?: boolean | null;
  } | null;
}

/** What the Stack form should badge, pre-fill and apply in one click. */
export interface MasterRecommendation {
  darkId: number | null;
  flatId: number | null;
  flatDarkId: number | null;
  /** The bias to select — either the lights' pedestal (no dark) or the one that
   *  lets a mismatched-exposure dark be scaled to these subs. */
  biasId: number | null;
  /** Turn "scale the dark to my subs" on with that bias. */
  scaleDark: boolean;
}

/**
 * Reconcile the two answers the server gives to "which masters for these subs?".
 *
 * `dark_master_id`…`bias_master_id` are the best master of each kind the library
 * *owns* — always something, with the form's own cautions explaining a poor
 * match. `confident` is what the **unattended** stack would actually bind: the
 * stricter "best one we're sure about", which is allowed to say nothing. They
 * can genuinely disagree — a gain-mismatched but exposure-perfect dark out-ranks
 * a gain-matched dark that only needs bias-scaling — and when they do, a watched
 * stack and a walk-away stack of the same subs were calibrated differently for
 * no reason the user could see.
 *
 * So: **prefer the confident pick wherever it has one**, and fall back to the
 * best available where it doesn't, so the form is never *less* helpful than it
 * was. Two couplings are deliberate rather than per-field:
 *
 *  - a **flat-dark** belongs to the flat it calibrates, so when the confident
 *    binding chose the flat it also owns the flat-dark answer (including
 *    "none") — the best-available flat-dark was matched to a different flat.
 *  - a **bias** is only offered beside a dark when it is there to *scale* that
 *    dark; otherwise it stays what it always was, the lights' pedestal when no
 *    dark is recommended (a dark already carries the bias).
 */
export function masterRecommendation(
  sug: MasterSuggestion | null | undefined,
): MasterRecommendation {
  const num = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? v : null;
  const c = sug?.confident ?? null;
  const cDark = num(c?.dark_master_id);
  const cFlat = num(c?.flat_master_id);
  const cBias = num(c?.bias_master_id);
  const darkId = cDark ?? num(sug?.dark_master_id);
  const flatId = cFlat ?? num(sug?.flat_master_id);
  const flatDarkId =
    cFlat !== null ? num(c?.flat_dark_master_id) : num(sug?.flat_dark_master_id);
  const scaleDark =
    Boolean(c?.scale_dark_to_light) && cDark !== null && cBias !== null;
  const biasId = cBias ?? (darkId === null ? num(sug?.bias_master_id) : null);
  return { darkId, flatId, flatDarkId, biasId, scaleDark };
}
