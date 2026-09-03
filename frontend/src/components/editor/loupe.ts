/** Pure geometry for the "check it at full size" window marker.
 *
 * The loupe reads a fixed number of *source* pixels — 512 by default — out of a
 * canvas that may be 150 megapixels. On the preview that is a small rectangle,
 * and showing where it is matters more than it sounds: at ×8 decimation a 512 px
 * window is 1/8th of the preview's width, and a beginner who can't see which
 * scrap of sky they are looking at learns nothing from it.
 */

const clampUnit = (v: number): number =>
  Number.isFinite(v) ? Math.min(Math.max(v, 0), 1) : 0.5;

export interface MarkerRect {
  /** All four in **percent** of the preview box, ready for CSS. */
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * Where the loupe's window sits on the preview, as CSS percentages — or `null`
 * when the preview's own size in source pixels isn't known yet.
 *
 * `shownSourceW`/`shownSourceH` are what the *rendered* preview covers measured
 * in source pixels (`render_width × proxy_scale`), not the preview's on-screen
 * size — the marker has to be a fraction of the picture, and the picture is what
 * the render covers. A window bigger than the preview clamps to the whole box,
 * which is the honest drawing of "this is all of it".
 *
 * The rectangle is clamped to stay inside the box, mirroring the server clamping
 * its window inside the canvas. The two agree exactly when the recipe has no
 * crop; with one they can differ by up to half a window at the very edge, which
 * is why this is only a guide — prefer :func:`loupeMarkerFromWindow` whenever the
 * server has answered, and keep this for the first paint (the marker must not
 * vanish while the render is in flight) and for a backend that doesn't send it.
 */
export function loupeMarkerRect(
  fx: number,
  fy: number,
  sizePx: number,
  shownSourceW: number | null | undefined,
  shownSourceH: number | null | undefined,
): MarkerRect | null {
  if (!shownSourceW || !shownSourceH || !(sizePx > 0)) return null;
  if (!Number.isFinite(shownSourceW) || !Number.isFinite(shownSourceH)) return null;
  const w = Math.min(1, sizePx / shownSourceW);
  const h = Math.min(1, sizePx / shownSourceH);
  const start = (centre: number, span: number) =>
    Math.min(Math.max(clampUnit(centre) - span / 2, 0), 1 - span);
  return {
    left: start(fx, w) * 100,
    top: start(fy, h) * 100,
    width: w * 100,
    height: h * 100,
  };
}

/**
 * Where in the preview a click landed, as a `(fx, fy)` fraction — the only thing
 * the browser can honestly report, since it knows neither the canvas size nor
 * what the recipe cropped. The server maps it back through the recipe's own crop.
 */
export function clickFraction(
  clientX: number, clientY: number, box: { left: number; top: number; width: number; height: number },
): { fx: number; fy: number } {
  if (!(box.width > 0) || !(box.height > 0)) return { fx: 0.5, fy: 0.5 };
  return {
    fx: clampUnit((clientX - box.left) / box.width),
    fy: clampUnit((clientY - box.top) / box.height),
  };
}

/**
 * The marker rectangle the **server** measured, when it sent one — its window
 * expressed as fractions of the rendered preview, which is the frame the marker
 * is drawn in.
 *
 * This is what `loupeMarkerRect` below can only approximate. That one re-derives
 * the rectangle from the click and clamps it inside the preview; the server's is
 * the window it actually cut, mapped back through the recipe's own crop, and it
 * is deliberately *not* clamped — a window clamped inside the canvas can hang
 * over a crop's edge, and drawing it clipped is the truth where sliding it inward
 * is not. Returns `null` when the backend didn't send it (older container, or a
 * degenerate crop), which is what keeps the guide below worth having.
 */
export function loupeMarkerFromWindow(
  win: {
    preview_x?: number; preview_y?: number;
    preview_width?: number; preview_height?: number;
  } | null | undefined,
): MarkerRect | null {
  if (!win) return null;
  const { preview_x: x, preview_y: y, preview_width: w, preview_height: h } = win;
  if (![x, y, w, h].every((v) => typeof v === "number" && Number.isFinite(v))) {
    return null;
  }
  if (!((w as number) > 0) || !((h as number) > 0)) return null;
  return {
    left: (x as number) * 100, top: (y as number) * 100,
    width: (w as number) * 100, height: (h as number) * 100,
  };
}

/**
 * Where in the whole picture the shown window actually sits, in words — from the
 * **server's** own clamped rectangle, not from the click.
 *
 * This is the thing the marker cannot promise. The marker is drawn against what
 * the *preview* covers, while the window is cut from the full canvas through the
 * recipe's crop, so with a crop the two can differ by up to half a window at the
 * very edge (see `loupeMarkerRect`). The sentence is the authoritative answer,
 * and it is the one a beginner asked for anyway: not "27.4 % across" but "the
 * top-left of your picture".
 *
 * Returns `null` — say nothing — when there is no window to describe, when the
 * numbers aren't finite, or when the window covers the whole canvas (there is no
 * "where" to name, and "all of it" is already obvious from the picture).
 */
export function loupeWhereText(
  win: {
    x: number; y: number; width: number; height: number;
    canvas_width: number; canvas_height: number;
  } | null | undefined,
): string | null {
  if (!win) return null;
  const { x, y, width, height, canvas_width: cw, canvas_height: ch } = win;
  const finite = [x, y, width, height, cw, ch].every((v) =>
    typeof v === "number" && Number.isFinite(v));
  if (!finite || !(cw > 0) || !(ch > 0) || !(width > 0) || !(height > 0)) return null;
  if (width >= cw && height >= ch) return null;

  // Thirds of the canvas, decided on the window's own centre. Thirds (not halves)
  // so "the middle" can be said when it is true — a beginner reading "the left"
  // about a centred window would trust the next sentence less.
  const band = (centre: number, span: number, names: [string, string, string]) => {
    const f = centre / span;
    return f < 1 / 3 ? names[0] : f < 2 / 3 ? names[1] : names[2];
  };
  const row = band(y + height / 2, ch, ["top", "middle", "bottom"]);
  const col = band(x + width / 2, cw, ["left", "centre", "right"]);
  const where = row === "middle" && col === "centre" ? "middle"
    : row === "middle" ? col
      : col === "centre" ? row
        : `${row}-${col}`;
  return `This is the ${where} of your picture.`;
}

/**
 * The one-line explanation under the full-size view: what it is, and why it is
 * not the same thing as the preview. Plain language, no jargon — "1:1" and
 * "decimation" mean nothing to the reader this is for.
 */
export function loupeCaption(sizePx: number, proxyScale: number | null | undefined): string {
  const px = Math.round(sizePx);
  const shrunk = proxyScale && proxyScale > 1
    ? ` The preview is shrunk to about a ${Math.round(proxyScale)}th of full size to stay quick, `
      + "so fine detail — sharpening, star size, speckles — reads differently there."
    : "";
  return `Every pixel, full size: a ${px} × ${px} piece of your finished picture, `
    + `edited exactly as the preview is.${shrunk}`;
}

/** How to draw the *preview* of the very same window, enlarged to sit under the
 *  full-size render — the CSS box for an `<img>` of the whole preview, in the
 *  pixel units of a `boxW × boxH` container. */
export interface LoupePreviewCrop {
  /** Width/height to render the whole preview image at, in px. */
  width: number;
  height: number;
  /** Where its top-left corner goes, in px, relative to the container (negative
   *  for every window that isn't at the preview's own top-left corner). */
  left: number;
  top: number;
}

/**
 * Scale and offset the preview image so the loupe's window fills a `boxW × boxH`
 * box — the "before" side of the full-size split.
 *
 * The question the split answers is *"and how different is that from what I've
 * been looking at?"*, which only means anything if both halves show the **same
 * patch of sky at the same size**. The server already says where its window
 * landed as fractions of the rendered preview (`preview_x/y/width/height`), so
 * this is arithmetic, not a second render: blow the preview up by `1/preview_width`
 * and slide its corner off-box by the window's own offset.
 *
 * Returns `null` when the server sent no rectangle (an older container, or a
 * degenerate crop) or the box hasn't been measured — the caller then offers no
 * comparison at all rather than a misaligned one, which would be worse than none.
 *
 * The result is deliberately *soft*: it is the decimated preview enlarged, not a
 * second render, and that softness is the finding rather than a defect. Say so
 * where it is drawn. Pure.
 */
export function loupePreviewCrop(
  win: {
    preview_x?: number; preview_y?: number;
    preview_width?: number; preview_height?: number;
  } | null | undefined,
  boxW: number,
  boxH: number,
): LoupePreviewCrop | null {
  if (!win) return null;
  const { preview_x: x, preview_y: y, preview_width: w, preview_height: h } = win;
  if (![x, y, w, h].every((v) => typeof v === "number" && Number.isFinite(v))) {
    return null;
  }
  if (!((w as number) > 0) || !((h as number) > 0)) return null;
  if (!(boxW > 0) || !(boxH > 0)) return null;
  const width = boxW / (w as number);
  const height = boxH / (h as number);
  return {
    width,
    height,
    left: -(x as number) * width,
    top: -(y as number) * height,
  };
}
