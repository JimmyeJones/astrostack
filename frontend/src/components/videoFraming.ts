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

// How hard to sharpen the finished picture. A lucky stack is an average, and
// averaging softens — every planetary tool finishes with a sharpening step for
// exactly that reason. The amounts must stay in step with `SHARPEN_PRESETS` in
// `seestack/video/detail.py`, which is what actually renders them.
//
// Here rather than on the Moon & Sun route for the same reason the crop copy is:
// both surfaces show the same finished picture, so both must describe it in the
// same words.
export const SHARPEN_PRESETS = [
  { value: "0", name: "Off", label: "Off — the plain stacked picture" },
  { value: "0.6", name: "Gentle", label: "Gentle — recommended" },
  { value: "1.2", name: "Medium", label: "Medium — more surface detail" },
  { value: "2", name: "Strong", label: "Strong — as far as it goes" },
];

export const DEFAULT_SHARPEN = "0";

/** How a finished picture says it was sharpened, or null when it wasn't.
 *
 * Named by the nearest preset rather than printed as a number: "1.2" means
 * nothing to the person looking at the picture, and a still made by a hand-written
 * API call can still be described in the same words as one made from the menu.
 */
export function sharpenNote(amount: number | undefined | null): string | null {
  if (!amount || !Number.isFinite(amount) || amount <= 0) return null;
  const preset = SHARPEN_PRESETS
    .filter((p) => Number(p.value) > 0)
    .reduce((best, p) => (
      Math.abs(Number(p.value) - amount) < Math.abs(Number(best.value) - amount) ? p : best
    ));
  return `Sharpening: ${preset.name} — surface detail lifted after stacking.`;
}

/** Fields the sharpening control reads off a finished picture. */
export interface SharpenFields {
  sharpen_amount?: number;
  sharpen_editable?: boolean;
}

/**
 * The offer to try a different sharpening on a picture that already exists — or
 * null when there is nothing to offer.
 *
 * Like the crop, this is a decision you can only really make by *looking at the
 * picture*, so the offer waits until there is one. It is null when the backend
 * can't do it without re-stacking (a still sharpened before the soft render was
 * kept beside it), because an offer that would fail is worse than none.
 */
export function sharpenOffer(
  result: SharpenFields | null | undefined,
  kind: SubjectKind,
): string | null {
  if (!result?.sharpen_editable) return null;
  const noun = subjectNoun(kind);
  if ((result.sharpen_amount ?? 0) > 0) {
    return (
      `Try a different amount — each one is rendered from the unsharpened `
      + `picture, so nothing builds up and "Off" gets you back exactly where `
      + `you started.`
    );
  }
  return (
    `Stacking averages your frames together, which makes the picture cleaner `
    + `but slightly softer. Bringing the detail back takes a moment and doesn't `
    + `re-stack anything — and you can change your mind as often as you like, `
    + `so it's worth seeing what your ${noun} looks like sharpened.`
  );
}

/** Which preset a picture's current strength corresponds to, for a menu (pure).
 *
 * Snapped to the nearest offered value so a still made by a hand-written API
 * call still selects something, rather than leaving the control blank. */
export function sharpenValueOf(result: SharpenFields | null | undefined): string {
  const amount = result?.sharpen_amount ?? 0;
  if (!Number.isFinite(amount) || amount <= 0) return DEFAULT_SHARPEN;
  return SHARPEN_PRESETS.reduce((best, p) => (
    Math.abs(Number(p.value) - amount) < Math.abs(Number(best.value) - amount) ? p : best
  )).value;
}
