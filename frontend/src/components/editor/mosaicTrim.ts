import type { EditOp, OpInstance } from "../../api/client";
import { insertOnCorrectSide } from "./stageConflicts";

/** Fractional (0..1) crop rectangle for the largest well-covered mosaic area. */
export interface TrimCrop {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** True when the recipe has an *enabled* geometry op (crop/rotate/resize) that
 * reshapes the frame. Pure. */
export function hasEnabledGeometryOp(ops: OpInstance[]): boolean {
  return ops.some((o) => o.enabled && o.id.startsWith("geometry."));
}

/** A stable key of just the *enabled geometry ops* (id + params, in order), so a
 * consumer (the coverage overlay) can refetch only when the geometry that reshapes
 * the frame actually changes — not on every tone-op tweak. Pure. */
export function geometryOpsKey(ops: OpInstance[]): string {
  return JSON.stringify(
    ops
      .filter((o) => o.enabled && o.id.startsWith("geometry."))
      .map((o) => ({ id: o.id, params: o.params })),
  );
}

/** CSS `left/top/width/height` (percent strings) placing the proposed-crop
 * rectangle over the preview image, from the fractional bounds. Pure. */
export function trimRectStyle(
  crop: TrimCrop,
): { left: string; top: string; width: string; height: string } {
  const pct = (v: number) => `${(v * 100).toFixed(2)}%`;
  return {
    left: pct(crop.x0),
    top: pct(crop.y0),
    width: pct(crop.x1 - crop.x0),
    height: pct(crop.y1 - crop.y0),
  };
}

/** Inline style for the preview *image box* — a wrapper sized to exactly the
 * displayed image so a percentage overlay (the proposed-crop rectangle) lines
 * up even when the preview is letterboxed.
 *
 * The preview `<img>` is width-100% but height-capped at ~62vh, so on a tall
 * (portrait) frame or a short window it pillarboxes inside its element and a
 * rectangle placed as a percentage of the *container* lands offset. Giving the
 * wrapper the image's own aspect ratio and capping its width so the
 * aspect-preserved height never exceeds the same cap makes the box equal the
 * shown image (no letterbox), so `trimRectStyle` percentages map straight onto
 * it. Falls back to plain full-width when the proxy dimensions are unknown
 * (histogram not loaded yet) — same as the old behaviour. Pure.
 */
export function previewBoxStyle(
  proxyWidth: number | undefined,
  proxyHeight: number | undefined,
  maxHeightVh = 62,
): { width: string; maxHeight?: string; maxWidth?: string; aspectRatio?: string; margin?: string } {
  if (!proxyWidth || !proxyHeight || proxyWidth <= 0 || proxyHeight <= 0
      || !Number.isFinite(proxyWidth) || !Number.isFinite(proxyHeight)) {
    return { width: "100%", maxHeight: `${maxHeightVh}vh` };
  }
  return {
    width: "100%",
    maxWidth: `calc(${maxHeightVh}vh * ${proxyWidth} / ${proxyHeight})`,
    aspectRatio: `${proxyWidth} / ${proxyHeight}`,
    margin: "0 auto",
  };
}

/** Fraction (0..1) of the *original* frame still shown after all *enabled*
 * `geometry.crop` ops in the recipe are applied, or `null` when there is no
 * enabled crop (or the crops together keep the whole frame — nothing visibly
 * removed). Each crop's fractional bounds are relative to the image entering
 * that op, so successive crops multiply. Mirrors the engine's clamp-to-[0,1] +
 * sort semantics (`_crop`) so the reported area matches what's actually shown.
 * Pure. */
export function cropCoverageFraction(ops: OpInstance[]): number | null {
  const crops = ops.filter((o) => o.enabled && o.id === "geometry.crop");
  if (crops.length === 0) return null;
  const clamp = (v: unknown, dflt: number): number => {
    const n = Number(v);
    return Math.min(Math.max(Number.isFinite(n) ? n : dflt, 0), 1);
  };
  let frac = 1;
  for (const o of crops) {
    const p = (o.params ?? {}) as Record<string, unknown>;
    let x0 = clamp(p.x0, 0), x1 = clamp(p.x1, 1);
    let y0 = clamp(p.y0, 0), y1 = clamp(p.y1, 1);
    if (x1 < x0) [x0, x1] = [x1, x0];
    if (y1 < y0) [y0, y1] = [y1, y0];
    frac *= (x1 - x0) * (y1 - y0);
  }
  return frac;
}

/** The integer percentage of the frame still shown after enabled crops, or
 * `null` when there's no crop or it rounds to the full frame (nothing to flag).
 * Pure. */
export function cropCoveragePct(ops: OpInstance[]): number | null {
  const frac = cropCoverageFraction(ops);
  if (frac == null) return null;
  const pct = Math.round(frac * 100);
  if (pct >= 100) return null; // no visible crop — don't nag
  return Math.max(pct, 0);
}

/** Drop every *enabled* `geometry.crop` op — the one-click "remove crop" action.
 * Pure: returns a new array, never mutates the input. Leaves a *disabled* crop
 * op alone (it isn't shrinking the view). */
export function removeCropOps(ops: OpInstance[]): OpInstance[] {
  return ops.filter((o) => !(o.enabled && o.id === "geometry.crop"));
}

/** Plain-language "keeps the central W% × H%" summary of a proposed crop. Pure. */
export function trimKeptLabel(crop: TrimCrop): string {
  const pctW = Math.round((crop.x1 - crop.x0) * 100);
  const pctH = Math.round((crop.y1 - crop.y0) * 100);
  return `keeps the central ${pctW}% × ${pctH}%`;
}

/** Set (or add) a `geometry.crop` op to the given fractional bounds — the
 * one-click "trim the ragged mosaic border" action. If a crop op already exists
 * it's updated in place and enabled (so re-trimming never stacks duplicate crops);
 * otherwise a fresh crop op is inserted on the correct side of the stretch. Pure:
 * returns a new ops array and never mutates the input. */
export function applyTrimCrop(
  ops: OpInstance[],
  crop: TrimCrop,
  specs: Record<string, EditOp>,
  makeUid: () => string,
): OpInstance[] {
  const bounds = { x0: crop.x0, y0: crop.y0, x1: crop.x1, y1: crop.y1 };
  if (ops.some((o) => o.id === "geometry.crop")) {
    return ops.map((o) =>
      o.id === "geometry.crop"
        ? { ...o, enabled: true, params: { ...o.params, ...bounds } }
        : o,
    );
  }
  const spec = specs["geometry.crop"];
  const defaults: Record<string, unknown> = {};
  spec?.params.forEach((p) => { defaults[p.key] = p.default; });
  const op: OpInstance = {
    uid: makeUid(),
    id: "geometry.crop",
    enabled: true,
    params: { ...defaults, ...bounds },
  };
  // With the crop spec known we can place it correctly (nonlinear → after the
  // stretch); without it (schema not loaded) fall back to appending.
  return spec ? insertOnCorrectSide(ops, op, specs) : [...ops, op];
}
