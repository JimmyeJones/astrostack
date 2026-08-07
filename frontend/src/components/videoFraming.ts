// The plain-language copy behind the Moon/Sun framing crop.
//
// It lives outside the Moon & Sun route because two surfaces now offer the same
// one-click crop — that page, and the Gallery card, which is the only place a
// user who has cleared the source video off the NAS still finds their picture.
// One copy of the wording means the two can never drift into describing the same
// picture differently.
//
// Pure and dependency-free (no React, no API types beyond the field shapes it
// reads), so it is cheap to test and safe for either route to import.

/** The kind of thing a capture is pointed at, as both surfaces spell it. */
export type SubjectKind = "lunar" | "solar" | "other";

/** Fields either surface's picture carries; both are optional because an older
 * backend omits them and an older still never had them measured. */
export interface FramingFields {
  crop_applied?: boolean;
  crop_available?: boolean;
  crop_trim_fraction?: number;
  source_width?: number;
  source_height?: number;
}

/** What to call the bright thing in the middle, in plain language (pure). */
export function subjectNoun(kind: SubjectKind): string {
  if (kind === "lunar") return "Moon";
  if (kind === "solar") return "Sun";
  return "subject";
}

/**
 * "Most of this picture is empty sky" — or null when there's nothing to say.
 *
 * Only ever shown for a still that was *not* cropped and where the backend
 * measured enough sky around the disk to be worth trimming, so it can't nag
 * about a picture that is already mostly subject.
 */
export function cropSuggestion(
  result: FramingFields | null | undefined,
  kind: SubjectKind,
): string | null {
  if (!result?.crop_available) return null;
  const pct = Math.round((result.crop_trim_fraction ?? 0) * 100);
  if (pct < 1) return null;
  return (
    `About ${pct}% of this picture is empty sky around the ${subjectNoun(kind)}. `
    + `Trimming it takes a moment and doesn't re-stack anything — the picture `
    + `itself stays exactly as it is, just without the empty sky.`
  );
}

/** The matching line once a still *has* been cropped (pure). */
export function cropNote(
  result: FramingFields | null | undefined,
  kind: SubjectKind,
): string | null {
  if (!result?.crop_applied) return null;
  const pct = Math.round((result.crop_trim_fraction ?? 0) * 100);
  const from = result.source_width && result.source_height
    ? ` (from ${result.source_width}×${result.source_height})`
    : "";
  return `Cropped to the ${subjectNoun(kind)} — trimmed ${pct}% of empty sky${from}.`;
}
