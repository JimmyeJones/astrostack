import type { OpInstance } from "../../api/client";

/** Strip a saved look's crop before it is applied to a picture ("Use my default",
 * a "My presets" pick). A crop is stored as fractions of the canvas it was framed
 * on, so replaying it on another picture cuts it by the wrong rectangle — a look
 * saved off a mosaic's Auto trim would take ~46 % off a single field. Framing
 * belongs to one picture; every other op carries over unchanged. The stored look
 * itself is untouched (the backend's Gallery batch drops it the same way). Pure. */
export function dropSavedCrop(ops: OpInstance[]): { ops: OpInstance[]; dropped: boolean } {
  const kept = ops.filter((o) => o.id !== "geometry.crop");
  return { ops: kept, dropped: kept.length !== ops.length };
}

/** The sentence a seed's notification adds when it left the crop behind. */
export const SAVED_CROP_DROPPED_NOTE =
  " Your saved crop wasn't carried — framing belongs to one picture.";
