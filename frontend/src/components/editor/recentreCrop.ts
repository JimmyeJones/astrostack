import type { StackRecentreCrop } from "../../api/client";
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
