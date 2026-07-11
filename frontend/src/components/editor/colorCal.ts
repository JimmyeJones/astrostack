// Pure helper: caption for which colour-calibration (white-balance) path the
// unattended auto-edit actually ran.
//
// The one-click Auto recipe runs `tone.color_calibrate` (gray-star), which needs
// enough stars to solve a photometric white balance. On a sparse-star field it
// falls back to a starless *background-neutral* balance (v0.107.9), and only truly
// gives up when even the sky can't be measured. The backend records the outcome
// (`mode_used`, `n_stars_used`) as per-run provenance; we turn it into a dimmed
// one-liner so a beginner who walked away knows whether — and how — their image
// was really colour-balanced. Read-only advisory; no image change.

import type { AutoColorCal } from "../../api/client";

// Returns { neutral, text } for the History Info panel's read-out of what the
// unattended auto-edit's white balance did, or null when unavailable (an old
// backend / a manual run with no stamped outcome, or an unrecognised mode).
// `neutral` (a reassuring ✓ tone) is true whenever a balance actually ran; the
// give-up case reads as a dimmed advisory.
export function autoColorCalCaption(
  cc: AutoColorCal | undefined | null,
): { neutral: boolean; text: string } | null {
  const mode = cc?.mode_used;
  if (!mode) return null;
  const n = typeof cc?.n_stars_used === "number" ? cc.n_stars_used : 0;
  if (mode === "gray_star" || mode === "gaia") {
    // A star-based solve. Guard the degenerate n=0 (shouldn't happen for these
    // modes, but never claim "0 stars ✓").
    if (n <= 0) return { neutral: true, text: "Auto white-balanced your image ✓" };
    return {
      neutral: true,
      text: `Auto white-balanced from ${n} star${n === 1 ? "" : "s"} ✓`,
    };
  }
  if (mode === "background_neutral") {
    return {
      neutral: true,
      text: "Auto balanced the colour from the background — too few stars ✓",
    };
  }
  if (mode === "none") {
    return {
      neutral: false,
      text: "Auto couldn't white-balance this image — try Neutralize background in the editor",
    };
  }
  return null;
}
