import type { IncomingCalibrationFolder } from "../api/client";

// Plain-language copy for the "we found calibration frames in your incoming
// folder" offer. A beginner with a Seestar has never heard of a master dark, but
// the frames are often already on the NAS — so the app can notice them and offer
// the build instead of making them learn what calibration is and go find the
// folder.
//
// Kept pure and separate from the card so the wording is unit-tested, exactly as
// `calibrationCoverage.ts` is.

const KIND_WORDS: Record<string, [string, string]> = {
  dark: ["dark frame", "dark frames"],
  flat: ["flat frame", "flat frames"],
  bias: ["bias frame", "bias frames"],
};

/** "8 dark frames" / "1 flat frame". */
export function framesPhrase(kind: string, n: number): string {
  const [one, many] = KIND_WORDS[kind] ?? [`${kind} frame`, `${kind} frames`];
  return `${n} ${n === 1 ? one : many}`;
}

/** What a master built from this folder would do for the user's pictures — the
 *  reason to press the button, in the one sentence a beginner needs. */
export function whatItDoes(kind: string): string {
  if (kind === "dark") {
    return "A master dark removes the sensor's own heat speckle and hot pixels "
      + "from every frame it's applied to.";
  }
  if (kind === "flat") {
    return "A master flat evens out the darker corners and any dust shadows on "
      + "the optics.";
  }
  return "A master bias removes the camera's fixed read-out pattern.";
}

/** The acquisition line under each folder: "8 dark frames · 30s · gain 80 · −5°C".
 *  Anything the frames didn't record is simply left out rather than shown as a
 *  dash — a beginner reading "gain —" learns nothing. */
export function folderSummaryLine(f: IncomingCalibrationFolder): string {
  const bits = [framesPhrase(f.kind, f.n_frames)];
  if (f.exposure_s) bits.push(`${f.exposure_s}s`);
  if (f.gain !== null && f.gain !== undefined) bits.push(`gain ${f.gain}`);
  if (f.sensor_temp_c !== null && f.sensor_temp_c !== undefined) {
    const t = Math.round(f.sensor_temp_c);
    bits.push(`${t < 0 ? "−" : ""}${Math.abs(t)}°C`);
  }
  return bits.join(" · ");
}

/** How we know — said out loud, because "we scanned your folder names" and "your
 *  frames told us" are very different promises, and only the second is true. */
export function whyWeThinkSo(f: IncomingCalibrationFolder): string {
  const kinds = Object.keys(f.declared ?? {});
  // A folder of flat-darks fills the *dark* slot but said "flat dark" — echo
  // what the frames actually said rather than relabelling the owner's frames.
  const said = kinds.includes("dark_flat") && !kinds.includes(f.kind)
    ? "flat-darks" : `${f.kind}s`;
  return `${f.n_sampled} of these frames say they are ${said}.`;
}

/** The card's headline, or null when there is nothing to offer (the card
 *  self-hides — an install whose camera writes no IMAGETYP never sees it). */
export function offerHeadline(
  folders: IncomingCalibrationFolder[],
): string | null {
  const fresh = folders.filter((f) => !f.have_master);
  if (fresh.length === 0) return null;
  if (fresh.length === 1) {
    return `You already have ${framesPhrase(fresh[0].kind, fresh[0].n_frames)}`;
  }
  const kinds = [...new Set(fresh.map((f) => f.kind))];
  return kinds.length === 1
    ? `You already have ${kinds[0]} frames in ${fresh.length} folders`
    : `You already have calibration frames in ${fresh.length} folders`;
}
