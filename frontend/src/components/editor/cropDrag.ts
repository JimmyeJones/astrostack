/**
 * Dragging the crop rectangle straight on the live preview.
 *
 * The `geometry.crop` op has existed for a long time, but the only way to aim it
 * was the four `Left / Top / Right / Bottom` sliders the descriptor-driven form
 * renders — *fractions of the frame*, typed while looking at a downscaled proxy
 * of a canvas that can be 12,000 px wide. "Crop in on the galaxy" is the single
 * most universally understood photo edit there is, and on this app it meant
 * arithmetic. That is the "clunky and confusing controls" complaint in
 * AGENTS.md §1, on the op where it costs a beginner the most.
 *
 * This module is the pure half of the fix: all the rectangle arithmetic —
 * reading the op's params, turning a pointer position into a fraction, applying
 * a handle drag, and describing the result in plain language — with no DOM and
 * no React, so it can be unit-tested exactly. `Editor.tsx` owns only the pointer
 * events and the overlay markup.
 *
 * **Why the rectangle is drawn over the *without-this-crop* render.** A crop
 * op's fractional bounds are relative to the image *entering* it, and the
 * ordinary preview shows the image *leaving* it — so dragging on the ordinary
 * preview would be dragging in the wrong coordinate space, and every drag would
 * compound against the last. Rendering the recipe with just this op bypassed
 * (machinery the per-op "show without this op" compare already provides) gives
 * exactly the crop's own input, so the fractions map 1:1 onto the box. That
 * equivalence only holds while no *other* enabled geometry op sits after this
 * one — see {@link cropDragBlockedReason}, which is why the mode declines
 * rather than guessing in that case.
 */

import type { OpInstance } from "../../api/client";
import type { TrimCrop } from "./mosaicTrim";

/** The smallest crop a drag may leave, as a fraction of each axis.
 *
 * The engine refuses a crop narrower than 2 *full-resolution* pixels
 * (`crop_bounds`), which on a real canvas is far below anything a finger or a
 * mouse can aim at. 2 % keeps every handle grabbable (≈21 px on a 1080 px axis),
 * keeps the rectangle visible while it is being shrunk, and stays comfortably
 * clear of the engine's degeneracy guard so what you drag is always what the
 * export applies. */
export const MIN_CROP_FRAC = 0.02;

/** Below this kept-area fraction the crop is worth remarking on in plain
 * language — a beginner who has dragged down to a tenth of the frame should be
 * told the picture gets much smaller, not left to discover it on export. */
const BIG_CROP_FRAC = 0.25;

/** Which part of the rectangle a drag is moving. The eight compass points are
 * the edge/corner handles; `move` slides the whole rectangle. */
export type CropHandle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "move";

/** Everything a drag needs to remember from the pointer-down that started it:
 * which handle was grabbed, the rectangle as it was then, and where inside the
 * box the pointer was (so `move` can be a delta rather than a jump-to-cursor). */
export interface CropDragStart {
  handle: CropHandle;
  crop: TrimCrop;
  fx: number;
  fy: number;
}

/** The whole frame — what a freshly-added crop op means, and what "reset" gives
 * back. */
export const FULL_CROP: TrimCrop = { x0: 0, y0: 0, x1: 1, y1: 1 };

const clamp01 = (v: number): number => Math.min(Math.max(v, 0), 1);

/** Read a crop op's params into a normalised fractional rectangle.
 *
 * Mirrors the engine's own clamp-to-[0,1]-then-sort semantics (`crop_bounds`),
 * so the rectangle drawn on screen is the rectangle that will be cut — including
 * for a hand-typed `x1 < x0`, which the engine sorts rather than rejects.
 * Anything missing or non-finite falls back to the whole frame. */
export function cropFromParams(params: Record<string, unknown> | undefined | null): TrimCrop {
  const read = (v: unknown, dflt: number): number => {
    const n = Number(v);
    return clamp01(Number.isFinite(n) ? n : dflt);
  };
  const p = params ?? {};
  let x0 = read(p.x0, 0), x1 = read(p.x1, 1);
  let y0 = read(p.y0, 0), y1 = read(p.y1, 1);
  if (x1 < x0) [x0, x1] = [x1, x0];
  if (y1 < y0) [y0, y1] = [y1, y0];
  return { x0, y0, x1, y1 };
}

/** The crop as the op's four params, rounded to the sliders' own 0.01 step so a
 * dragged value and a typed one are the same kind of number (and the undo
 * history doesn't fill with 17-decimal noise). */
export function cropToParams(crop: TrimCrop): Record<string, number> {
  const q = (v: number) => Math.round(clamp01(v) * 1000) / 1000;
  return { x0: q(crop.x0), y0: q(crop.y0), x1: q(crop.x1), y1: q(crop.y1) };
}

/** Where a pointer sits inside the preview image box, as a (0..1, 0..1)
 * fraction. Clamped, so a drag that leaves the box pins to the edge instead of
 * running away. */
export function pointerFraction(
  clientX: number,
  clientY: number,
  box: { left: number; top: number; width: number; height: number },
): { fx: number; fy: number } {
  const fx = box.width > 0 ? (clientX - box.left) / box.width : 0;
  const fy = box.height > 0 ? (clientY - box.top) / box.height : 0;
  return { fx: clamp01(fx), fy: clamp01(fy) };
}

/** Apply a drag to the rectangle: the pointer is now at `(fx, fy)` and `start`
 * records the grab.
 *
 * Edge and corner handles move only the edges they name, and are stopped by
 * {@link MIN_CROP_FRAC} against the *opposite* edge — the opposite edge never
 * moves, so shrinking to the minimum pins rather than flipping the rectangle
 * inside out. `move` slides the whole rectangle by the pointer's delta and is
 * clamped at the frame border **with its size preserved**, so pushing a crop
 * into a corner parks it there instead of squashing it. Pure. */
export function applyCropDrag(start: CropDragStart, fx: number, fy: number): TrimCrop {
  const c = start.crop;
  if (start.handle === "move") {
    const w = c.x1 - c.x0, h = c.y1 - c.y0;
    const dx = Math.min(Math.max(fx - start.fx, -c.x0), 1 - c.x1);
    const dy = Math.min(Math.max(fy - start.fy, -c.y0), 1 - c.y1);
    const x0 = clamp01(c.x0 + dx), y0 = clamp01(c.y0 + dy);
    return { x0, y0, x1: clamp01(x0 + w), y1: clamp01(y0 + h) };
  }
  const px = clamp01(fx), py = clamp01(fy);
  let { x0, y0, x1, y1 } = c;
  if (start.handle.includes("w")) x0 = Math.min(px, x1 - MIN_CROP_FRAC);
  if (start.handle.includes("e")) x1 = Math.max(px, x0 + MIN_CROP_FRAC);
  if (start.handle.includes("n")) y0 = Math.min(py, y1 - MIN_CROP_FRAC);
  if (start.handle.includes("s")) y1 = Math.max(py, y0 + MIN_CROP_FRAC);
  return { x0: clamp01(x0), y0: clamp01(y0), x1: clamp01(x1), y1: clamp01(y1) };
}

/** Placement (CSS percentage strings) and cursor for each of the eight
 * edge/corner handles, so the overlay's markup is a map over data rather than
 * eight hand-written blocks that can drift apart. Each entry's `left`/`top` is
 * the handle's *centre*; the caller translates by half its own size. Pure. */
export function cropHandlePositions(
  crop: TrimCrop,
): { handle: CropHandle; left: string; top: string; cursor: string }[] {
  const midX = (crop.x0 + crop.x1) / 2;
  const midY = (crop.y0 + crop.y1) / 2;
  const pct = (v: number) => `${(v * 100).toFixed(2)}%`;
  const spec: [CropHandle, number, number, string][] = [
    ["nw", crop.x0, crop.y0, "nwse-resize"],
    ["n", midX, crop.y0, "ns-resize"],
    ["ne", crop.x1, crop.y0, "nesw-resize"],
    ["e", crop.x1, midY, "ew-resize"],
    ["se", crop.x1, crop.y1, "nwse-resize"],
    ["s", midX, crop.y1, "ns-resize"],
    ["sw", crop.x0, crop.y1, "nesw-resize"],
    ["w", crop.x0, midY, "ew-resize"],
  ];
  return spec.map(([handle, x, y, cursor]) => ({
    handle, left: pct(x), top: pct(y), cursor,
  }));
}

/** True when the crop keeps the whole frame — i.e. the op currently does
 * nothing, so there is nothing to undo and nothing to warn about. */
export function isFullFrame(crop: TrimCrop): boolean {
  return crop.x1 - crop.x0 >= 0.999 && crop.y1 - crop.y0 >= 0.999;
}

/** Plain-language "what this crop keeps", for the caption on the picture.
 *
 * Percentages of each axis rather than of the area, because that is what the
 * rectangle on screen actually shows — an area figure ("keeps 30 %") reads as a
 * much harsher cut than the same rectangle looks. Pure. */
export function cropKeptLabel(crop: TrimCrop): string {
  if (isFullFrame(crop)) return "Keeping the whole picture";
  const pctW = Math.round((crop.x1 - crop.x0) * 100);
  const pctH = Math.round((crop.y1 - crop.y0) * 100);
  return `Keeping ${pctW}% × ${pctH}% of the picture`;
}

/** A gentle note when the drag has taken a big bite out of the frame, or `null`
 * when it hasn't. Deliberately not a warning: cropping hard is a legitimate
 * thing to want (a small galaxy on a wide field), it just costs pixels, and a
 * beginner should hear that before they export rather than after. Pure. */
export function bigCropNote(crop: TrimCrop): string | null {
  const area = Math.max(crop.x1 - crop.x0, 0) * Math.max(crop.y1 - crop.y0, 0);
  if (!(area > 0) || area >= BIG_CROP_FRAC) return null;
  return "That's a big crop — the saved picture will be much smaller, "
    + "and enlarging it later can't put the detail back.";
}

/** Why dragging can't be offered for this crop op, or `null` when it can.
 *
 * The rectangle is drawn over the render of the recipe with *this* op bypassed,
 * which equals the crop's own input only while nothing after it reshapes the
 * frame. A rotate or resize later in the recipe breaks that, and a rectangle
 * that is confidently in the wrong place is worse than no rectangle — so say so
 * and leave the sliders, exactly as the sky-overlay placement declines rather
 * than guessing. Pure. */
export function cropDragBlockedReason(ops: OpInstance[], uid: string): string | null {
  const i = ops.findIndex((o) => o.uid === uid);
  if (i < 0) return null;
  // *Any* enabled geometry op after this one breaks the equivalence, a second
  // crop included: the bypassed render would then show that crop's output rather
  // than this one's input.
  const after = ops.slice(i + 1).some((o) => o.enabled && o.id.startsWith("geometry."));
  if (after) {
    return "Dragging is off while another Crop, Rotate or Resize sits after this "
      + "one — move this crop last, or use the sliders below.";
  }
  return null;
}
