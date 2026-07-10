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
