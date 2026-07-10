/** Pure geometry for the editor's split before/after compare.
 *
 * Compare's default mode toggles the whole preview between "Original" and
 * "edited", so you have to flip back and forth and remember the difference. The
 * split mode instead overlays the Original on top of the edited preview and
 * clips it with a draggable vertical divider, so you judge exactly what an edit
 * changed in one frame — the left of the divider shows the Original, the right
 * shows the edit. These helpers turn a pointer position into the divider
 * fraction and the CSS clip that reveals only the left (Original) portion, kept
 * pure so a Vitest can exercise the drag without a DOM. */

/** Fraction [0,1] of the image box's width where the divider sits, from a
 * pointer's `clientX` and the box's left edge + width (a `getBoundingClientRect`
 * result). Clamped to [0,1] so the handle can never leave the image; a
 * zero/negative width (unmeasured box) falls back to the centre. Pure. */
export function splitFraction(clientX: number, rectLeft: number, rectWidth: number): number {
  if (!(rectWidth > 0)) return 0.5;
  const f = (clientX - rectLeft) / rectWidth;
  return Math.min(1, Math.max(0, f));
}

/** CSS `clip-path` that reveals only the left `fraction` of an element and hides
 * the rest — used on the Original overlay so it shows on the left of the divider
 * and the edited image below shows through on the right. `inset(top right bottom
 * left)`, so the right inset is `100·(1 − fraction)%`. Pure. */
export function splitClipLeft(fraction: number): string {
  const pct = Math.min(100, Math.max(0, fraction * 100));
  return `inset(0 ${100 - pct}% 0 0)`;
}

/** The divider's `left` CSS offset as a percentage string, clamped to the box.
 * Pure. */
export function splitLeftPct(fraction: number): string {
  const pct = Math.min(100, Math.max(0, fraction * 100));
  return `${pct}%`;
}

/** The ops that reshape the frame's canvas — mirrors
 * `seestack/edit/ops/geometry.py::GEOMETRY_OP_IDS`. Disabling one changes the
 * frame's shape. */
export const RESHAPING_OP_IDS = [
  "geometry.crop", "geometry.rotate", "geometry.resize",
] as const;

/** Whether an op reshapes the frame (crop/rotate/resize). A *per-op* compare
 * overlays the with-op preview on the without-op render and clips both under one
 * divider, sized to the (cropped) rendered box; when the toggled op is a
 * reshaping one the without-op image is a *different shape* and letterboxes at a
 * different scale, so the two halves can't be pixel-aligned. The whole-recipe
 * Split sidesteps this by rendering its Original through *all* enabled geometry
 * ops so the shapes match, but the per-op compare must toggle exactly one op and
 * has no such option — so it shouldn't offer a per-op split/swap for these ops.
 * Pure. */
export function reshapesFrame(opId: string): boolean {
  return (RESHAPING_OP_IDS as readonly string[]).includes(opId);
}

/** Build the op list that renders *another look* (a preset or the Auto recipe) as
 * the "before" side of the split divider. The right side of the divider is the
 * user's current edit, whose frame shape is fixed by *its* enabled geometry ops
 * (crop/rotate/resize); so for the two halves to line up under the divider the
 * look must be shown on the *same* frame. We therefore drop the look's own
 * geometry ops and append the current recipe's enabled geometry ops instead — the
 * comparison becomes "this look's tone/colour/detail vs mine, on the same view",
 * which is exactly the useful question when choosing between looks (and mirrors
 * how the Original split shares the edit's framing). With no geometry op on either
 * side this is just the look's ops verbatim. Pure. */
export function lookCompareOps<T extends { id: string }>(
  lookOps: T[], currentGeometryOps: T[],
): T[] {
  return [
    ...lookOps.filter((o) => !o.id.startsWith("geometry.")),
    ...currentGeometryOps,
  ];
}
