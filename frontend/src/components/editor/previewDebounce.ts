import type { EditOp, OpInstance } from "../../api/client";

/** Live-preview debounce (ms) for a light pipeline — quick enough that light
 * edits (levels, saturation) feel responsive. */
export const LIGHT_DEBOUNCE_MS = 250;
/** Longer settle when an *enabled, expensive* op is present, so dragging any
 * slider re-renders only the value you land on rather than every intermediate
 * frame through a slow op (deconvolution, wavelet denoise). */
export const HEAVY_DEBOUNCE_MS = 600;

/** Choose the preview debounce for the current pipeline. A heavy op anywhere in
 * the *enabled* recipe makes the whole preview settle longer, since each render
 * runs the full recipe through that op. Pure — keyed off the ops' `heavy` spec
 * hint, so it degrades to the light debounce when the schema doesn't mark any. */
export function previewDebounceMs(
  ops: OpInstance[],
  specs: Record<string, EditOp>,
): number {
  const hasHeavy = ops.some((o) => o.enabled && specs[o.id]?.heavy);
  return hasHeavy ? HEAVY_DEBOUNCE_MS : LIGHT_DEBOUNCE_MS;
}
