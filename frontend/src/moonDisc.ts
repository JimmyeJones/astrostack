import type { ScaleBar } from "./api/client";

/**
 * "Moon for scale" — how big to draw a disc the true angular size of the full
 * Moon over a picture, and when not to draw one at all.
 *
 * The scale bar already answers "how big is this piece of sky?" in words
 * ("the whole frame is about 2.5 full Moons wide"). That sentence asks a
 * beginner to do arithmetic against something they can only picture; a faint
 * circle beside the nebula is the same fact, seen rather than computed. This
 * module owns the two numbers that decide it, so the browser overlay and the
 * baked share JPEG (`seestack/skymarks.py`) can't disagree about the disc's
 * size or about when it appears — `tests/test_moon_disc_mirror.py` pins both
 * against the engine's own constants.
 */

/**
 * The full Moon's mean apparent diameter in arcseconds (~31′). Mirrors
 * `seestack.scalebar.MOON_DIAMETER_ARCSEC`.
 */
export const MOON_DIAMETER_ARCSEC = 31.0 * 60.0;

/**
 * The disc is drawn only while its diameter stays within this share of the
 * picture's **short** side. Past it the Moon isn't a *mark* on the picture, it
 * is most of the picture, and a circle that big reads as damage rather than as
 * a size cue — which is exactly the field where the bar's own sentence already
 * says the honest thing in words. Mirrors
 * `seestack.skymarks.MOON_DISC_MAX_SHORT_FRACTION`.
 */
export const MOON_DISC_MAX_SHORT_FRACTION = 0.5;

/**
 * The full Moon's diameter as a fraction of the picture's width, from a scale
 * bar — the mirror of `seestack.scalebar.ScaleBar.moon_fraction`, and derived
 * the same way, from the bar's own `fraction`.
 *
 * That derivation is the whole trick: `fraction` is already re-based wherever
 * the picture isn't the whole canvas (an auto-edit crop, a North-up turn that
 * grew the frame), so the disc follows those without any arithmetic of its own
 * and cannot be left behind when a new case is added. `0` for a bar that can't
 * answer.
 */
export function moonDiscFraction(bar: ScaleBar | null | undefined): number {
  if (!bar) return 0;
  const { arcsec, fraction } = bar;
  if (!Number.isFinite(arcsec) || !Number.isFinite(fraction)) return 0;
  if (!(arcsec > 0) || !(fraction > 0)) return 0;
  return (fraction * MOON_DIAMETER_ARCSEC) / arcsec;
}

/**
 * Is a Moon disc worth offering on a picture of these proportions?
 *
 * True only when the bar can answer at all *and* the disc stays within
 * {@link MOON_DISC_MAX_SHORT_FRACTION} of the picture's short side. Asked
 * against the image's own dimensions rather than any rendered box, because a
 * contain-fit scales both axes alike — so the answer is the same on a phone
 * card and a full-screen lightbox, and a control can be offered (or withheld)
 * before anything has been measured.
 */
export function moonDiscFits(
  bar: ScaleBar | null | undefined, imgWidth: number, imgHeight: number,
): boolean {
  if (!(imgWidth > 0) || !(imgHeight > 0)) return false;
  const moonFraction = moonDiscFraction(bar);
  if (!(moonFraction > 0)) return false;
  const diameter = moonFraction * imgWidth;
  return diameter <= Math.min(imgWidth, imgHeight) * MOON_DISC_MAX_SHORT_FRACTION;
}

/**
 * On-screen geometry for the Moon disc over a contain-fit image — the sibling of
 * `scaleBarLayout`/`compassLayout` in `AnnotatedImage`, kept here with the
 * constants it depends on.
 *
 * Returns `null` when there is nothing to place: no usable bar, a box not yet
 * measured, or a Moon too big to be a mark on this picture. Pure, so the
 * geometry is unit-testable without a DOM.
 */
export function moonDiscLayout(
  bar: ScaleBar | null | undefined,
  imgWidth: number,
  imgHeight: number,
  boxW: number,
  boxH: number,
): { diameterPx: number } | null {
  if (imgWidth <= 0 || imgHeight <= 0 || boxW <= 0 || boxH <= 0) return null;
  // The same "is this still a mark?" test the bake applies — and the same one a
  // control asks before offering the toggle, so nothing can offer a disc this
  // then declines to place.
  if (!moonDiscFits(bar, imgWidth, imgHeight)) return null;
  const scale = Math.min(boxW / imgWidth, boxH / imgHeight);
  const diameterPx = moonDiscFraction(bar) * imgWidth * scale;
  if (!(diameterPx > 0)) return null;
  return { diameterPx };
}
