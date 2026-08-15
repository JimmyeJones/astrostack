import type { StackRecentreCrop, StackRecentreRefusal } from "../../api/client";
import type { TrimCrop } from "./mosaicTrim";

/** The re-centring crop as the editor's fractional crop rectangle, or `null`
 * when there is no honest offer to make.
 *
 * The backend already refuses to propose a crop that can't help (a centred
 * picture, a clipped object, or a crop that would gut the frame), and an older
 * backend omits the field entirely — so this is mostly a shape guard: only a
 * rectangle with real extent in both axes and bounds inside 0..1 becomes a
 * button. Pure. */
export function recentreCropRect(
  recentre: StackRecentreCrop | null | undefined,
): TrimCrop | null {
  if (!recentre) return null;
  const { x0, y0, x1, y1 } = recentre;
  const ok = [x0, y0, x1, y1].every((v) => Number.isFinite(v) && v >= 0 && v <= 1);
  if (!ok || x1 <= x0 || y1 <= y0) return null;
  return { x0, y0, x1, y1 };
}

/** Plain-language "how much of the picture this keeps" summary for the
 * re-centring crop — the beginner's honest cost of taking the offer. Pure. */
export function recentreKeptLabel(crop: TrimCrop): string {
  const pct = Math.round((crop.x1 - crop.x0) * (crop.y1 - crop.y0) * 100);
  return `keeps ${Math.min(99, Math.max(1, pct))}% of the picture`;
}

/** How much of the picture a fraction is, in words a beginner reads without
 * doing arithmetic: 0.21 → "a fifth". Falls back to a percentage below the
 * smallest simple fraction, because "a twentieth" is worse than "5%". Pure. */
export function keptFractionWords(kept: number): string {
  const WORDS: [number, string][] = [
    [1 / 2, "half"], [2 / 5, "two fifths"], [1 / 3, "a third"], [1 / 4, "a quarter"],
    [1 / 5, "a fifth"], [1 / 6, "a sixth"], [1 / 8, "an eighth"], [1 / 10, "a tenth"],
  ];
  if (kept < 1 / 12) return `${Math.max(1, Math.round(kept * 100))}%`;
  let best = WORDS[0];
  for (const w of WORDS) {
    if (Math.abs(w[0] - kept) < Math.abs(best[0] - kept)) best = w;
  }
  return best[1];
}

/** The honest line for a picture that landed *too* far off-centre to rescue by
 * cropping — the case where the app used to go quiet on exactly the pictures it
 * had the most to say about. Returns `null` for every other refusal: "the object
 * is bigger than the frame" is already said by the `partial` verdict, "already
 * centred" needs no words, and an unmeasurable picture has nothing honest to add.
 * Pure. */
export function recentreRefusalLine(
  refused: StackRecentreRefusal | null | undefined,
  objectName: string,
): string | null {
  if (!refused || refused.reason !== "too_destructive") return null;
  const kept = refused.kept;
  if (typeof kept !== "number" || !Number.isFinite(kept) || kept <= 0 || kept >= 1) {
    return null;
  }
  return `Cropping ${objectName} back to the middle would leave only about `
    + `${keptFractionWords(kept)} of the picture, so it's better to re-point next `
    + "session than to crop this one.";
}
