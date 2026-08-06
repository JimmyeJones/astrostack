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
