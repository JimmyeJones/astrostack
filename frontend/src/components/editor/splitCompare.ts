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
