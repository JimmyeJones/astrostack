import type { EditOp, OpInstance } from "../../api/client";

/** Live-preview debounce (ms) for a light pipeline — quick enough that light
 * edits (levels, saturation) feel responsive. */
export const LIGHT_DEBOUNCE_MS = 250;
/** Longer settle when an *enabled, expensive* op is present, so dragging any
 * slider re-renders only the value you land on rather than every intermediate
 * frame through a slow op (deconvolution, wavelet denoise). */
export const HEAVY_DEBOUNCE_MS = 600;
/** The settle for a picture whose renders are measured in **seconds** — a mosaic
 * canvas at this owner's scale, or a slow box. Also the ceiling: however long a
 * render turns out to take, the editor must still answer a click promptly enough
 * to feel alive, so a 30 s render does not buy a 15 s settle. */
export const SLOW_DEBOUNCE_MS = 1200;

/** A render at least this slow earns :data:`HEAVY_DEBOUNCE_MS`, and one at least
 * :data:`SLOW_RENDER_MS` earns :data:`SLOW_DEBOUNCE_MS`. The two numbers come
 * from what a render of the one-click Auto recipe actually costs across the
 * canvases this editor opens — 0.2–0.3 s on a single field, 0.7 s on a small
 * mosaic, 2.8–5.2 s on a proxy the size of the owner's own
 * (`webapp/edit_resume_cache.py` measures all four) — so each rung names a
 * class of picture rather than a point on a curve. */
export const HEAVY_RENDER_MS = 500;
export const SLOW_RENDER_MS = 1200;

/** The settle a render of `ms` earns on its own, or `undefined` when there is no
 * usable measurement yet (first open, a failed render, a stubbed clock).
 *
 * **Three rungs, not a formula, and that is the point.** `useDebouncedValue`
 * re-arms a *pending* timer whenever its `wait` changes, so a debounce that
 * tracked every render's jitter would keep restarting the settle the user is
 * already waiting on. Two renders of the same picture have to land on the same
 * number, and a ladder is the cheapest way to promise that. */
export function settleForRenderMs(ms: number | undefined | null): number | undefined {
  if (typeof ms !== "number" || !Number.isFinite(ms) || ms <= 0) return undefined;
  if (ms >= SLOW_RENDER_MS) return SLOW_DEBOUNCE_MS;
  if (ms >= HEAVY_RENDER_MS) return HEAVY_DEBOUNCE_MS;
  return LIGHT_DEBOUNCE_MS;
}

/** Choose the preview debounce for the current pipeline.
 *
 * Two inputs, and they answer different halves of "how long is one render?".
 * A heavy op anywhere in the *enabled* recipe makes the whole preview settle
 * longer, since each render runs the full recipe through that op — that is the
 * `heavy` spec hint, and it is a property of the **op**. But the cost it stands
 * in for is dominated by the **picture**: with no heavy op enabled at all, the
 * same Auto recipe is 0.2 s on a single field and 2.8 s on a proxy the size of
 * the owner's mosaic, so the op hint alone settles a 2.8 s render in 250 ms and
 * fires another render on every quarter-second pause. `lastRenderMs` — how long
 * the previous render of *this* picture actually took — closes that, and it is
 * measured rather than derived from the canvas size on purpose: the same mosaic
 * renders at very different speeds on different boxes, and no constant in this
 * repo can know the owner's NAS.
 *
 * Pure, and the op hint is still a floor: a heavy op never settles in less than
 * :data:`HEAVY_DEBOUNCE_MS` however fast the last render happened to be. With no
 * measurement it is exactly the old behaviour. */
export function previewDebounceMs(
  ops: OpInstance[],
  specs: Record<string, EditOp>,
  lastRenderMs?: number | null,
): number {
  const hasHeavy = ops.some((o) => o.enabled && specs[o.id]?.heavy);
  const base = hasHeavy ? HEAVY_DEBOUNCE_MS : LIGHT_DEBOUNCE_MS;
  const measured = settleForRenderMs(lastRenderMs);
  return measured === undefined ? base : Math.max(base, measured);
}
