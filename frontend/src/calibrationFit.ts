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
}

/** The target's frame size, as reported by `calibration-suggestions.params`. */
export interface FrameDims {
  width_px?: number | null;
  height_px?: number | null;
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
): string {
  return masterFitsFrames(master, frames) ? "" : " — wrong size for this target";
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
