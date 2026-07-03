import type { OpInstance } from "../../api/client";

// The star-mask overlay shows what the editor treats as "stars" for the star ops.
// The endpoint's `size_px` matches the ops' own star size: `stars.reduce` gates on
// 2× its `size`, `stars.boost_nebula` on `size` directly (see the endpoint
// docstring in webapp/routers/editor.py). So the overlay must be sized from the
// *selected* star op's current `size`, or it silently misrepresents what the op
// actually gates. Returns undefined for a non-star (or no) selection, so the
// overlay falls back to the endpoint's default 4 px mask.
export function starMaskSizePx(op: OpInstance | null | undefined): number | undefined {
  if (!op) return undefined;
  const size = Number(op.params?.size);
  if (op.id === "stars.reduce") return Number.isFinite(size) ? 2 * size : 4;
  if (op.id === "stars.boost_nebula") return Number.isFinite(size) ? size : 4;
  return undefined;
}
