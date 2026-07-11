// Pure helper: caption for the finished picture's residual sky-background colour
// cast.
//
// The editor already has SCNR (green removal) and colour-calibration, but a
// beginner has no way to *see* whether their sky background actually ended up
// neutral. The backend measures the robust per-channel sky-background medians on
// the post-recipe display image (the sky population — pixels at/below the
// luminance median — so stars/target don't pull it) and returns a
// `sky_cast` verdict on the histogram. We turn it into a dimmed one-liner so the
// user gets an honest read-out of their finished background. Read-only advisory;
// no image change.

export interface SkyCastInfo {
  r: number | null;
  g: number | null;
  b: number | null;
  neutral: boolean;
  // "neutral" | "unknown" | one of red/green/blue/cyan/magenta/yellow
  cast: string;
  deviation: number;
}

export interface SkyCastHistogram {
  sky_cast?: SkyCastInfo | null;
  already_display?: boolean;
}

// Human-readable name for a measured cast colour (identity for the primary
// colours; the complements read more naturally spelled out).
const CAST_LABEL: Record<string, string> = {
  red: "red",
  green: "green",
  blue: "blue",
  cyan: "cyan",
  magenta: "magenta",
  yellow: "yellow",
};

// Returns { neutral, text } describing the finished sky background, or null when
// the measurement is unavailable (empty/failed stack, or an old backend that
// doesn't send `sky_cast`). `neutral` lets the caller pick a reassuring ✓ tone
// vs an advisory tone.
export function skyCastCaption(
  info: SkyCastHistogram | undefined | null,
): { neutral: boolean; text: string } | null {
  const sc = info?.sky_cast;
  if (!sc || sc.cast === "unknown") return null;
  if (sc.neutral || sc.cast === "neutral") {
    return { neutral: true, text: "Sky background: neutral ✓" };
  }
  const colour = CAST_LABEL[sc.cast] ?? sc.cast;
  // Deviation is a fraction of the [0,1] display range; ~1–3% reads as "slight".
  const strong = sc.deviation >= 0.03;
  return {
    neutral: false,
    text: `Sky background has a ${strong ? "" : "slight "}${colour} cast`,
  };
}

// --- one-click "neutralise background" fix ---------------------------------
//
// When the read-out reports a residual sky-background cast, offer a one-click fix
// that appends a `tone.neutralize_background` op. That op measures the sky cast at
// render time and balances each channel's sky level to the darkest, so the
// background goes neutral grey — an undoable step, exactly like the Auto-curve /
// trim buttons. It's appended at the very *end* of the recipe so it runs in
// display space (after the stretch and any colour ops), which is where the cast is
// measured; the caller guards that this lands in display space (an enabled stretch
// or an already-display re-open) so the fix always actually takes effect.

import type { EditOp, OpInstance } from "../../api/client";

export const NEUTRALIZE_BG_OP_ID = "tone.neutralize_background";

// True when a one-click neutralise is worth offering: the read-out shows a real
// (non-neutral, non-unknown) cast, the correction will land in display space
// (an enabled stretch is present, or the run is already display-space), and there
// isn't already an enabled neutralise op sitting at the end doing the job. Pure.
export function canNeutraliseSkyCast(
  info: SkyCastHistogram | undefined | null,
  ops: OpInstance[],
  hasEnabledStretch: boolean,
): boolean {
  const sc = info?.sky_cast;
  if (!sc || sc.cast === "unknown" || sc.neutral || sc.cast === "neutral") return false;
  if (!hasEnabledStretch && !info?.already_display) return false;
  // Don't stack a second neutralise when the last op already is one (enabled);
  // a lingering cast then is within the read-out's noise, not worth another op.
  const enabled = ops.filter((o) => o.enabled);
  const last = enabled[enabled.length - 1];
  if (last && last.id === NEUTRALIZE_BG_OP_ID) return false;
  return true;
}

// Append a fresh `tone.neutralize_background` op to the end of the recipe — the
// one-click "neutralise the sky cast" action. Appending (not inserting on the
// stretch's correct side) is deliberate: it must run *last*, in display space,
// so it neutralises the cast the read-out actually measured. Pure: returns a new
// array, never mutates the input. Falls back to returning the input unchanged when
// the op schema isn't loaded yet.
export function neutraliseBackgroundOps(
  ops: OpInstance[],
  specs: Record<string, EditOp>,
  makeUid: () => string,
): OpInstance[] {
  const spec = specs[NEUTRALIZE_BG_OP_ID];
  if (!spec) return ops;
  const params: Record<string, unknown> = {};
  spec.params.forEach((p) => { params[p.key] = p.default; });
  const op: OpInstance = { uid: makeUid(), id: NEUTRALIZE_BG_OP_ID, enabled: true, params };
  return [...ops, op];
}

// As above, but phrased for a result the user *didn't* drive — the History Info
// panel's read-out of what the unattended auto-edit produced, sitting under the
// "Auto-edited: …" note. Same measurement, framed as "what Auto's colour path
// landed" rather than a live editor read-out. Returns null when unavailable.
export function autoSkyCastCaption(
  info: SkyCastHistogram | undefined | null,
): { neutral: boolean; text: string } | null {
  const sc = info?.sky_cast;
  if (!sc || sc.cast === "unknown") return null;
  if (sc.neutral || sc.cast === "neutral") {
    return { neutral: true, text: "Auto's background came out neutral ✓" };
  }
  const colour = CAST_LABEL[sc.cast] ?? sc.cast;
  const strong = sc.deviation >= 0.03;
  return {
    neutral: false,
    text: `Auto's background came out with a ${strong ? "" : "slight "}${colour} cast`,
  };
}
