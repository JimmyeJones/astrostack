// Pure helper: caption for "hot-pixel removal isn't shown on this preview".
//
// Hot-pixel repair only makes sense on the detector's own pixel grid: it decides
// a pixel is a defect because its 3×3 neighbourhood — and the other two colour
// channels — are still at sky. The live-preview proxy is decimated by *striding*,
// so a real 2–3 px star lands on one lone proxy pixel with sky all around it in
// every channel: the exact signature of a defect. Previewing the op therefore
// erased stars the export never touches (measured: 369 of 483 bright stars lost
// more than half their brightness at proxy step 3, against none in the export).
// There is no proxy-scale version of the test, so the preview skips the op and
// the backend flags it (`hot_pixels_preview_skipped`); we say so plainly rather
// than let the preview show a starless picture the export won't produce.
// Advisory only — the export still removes hot pixels.
//
// It used to stop at "your export still gets the cleanup", which is reassurance
// without an answer: this op carries a **Threshold (σ)** slider (2–10), and a
// reader told the preview shows none of it has a knob and no way to set it. The
// full-size check is that way — it renders at `proxy_scale == 1`, where
// `hot_pixels_skipped_on_proxy` is False and `_hot_pixels` really runs — and it
// sits directly under this sentence. v0.445.3 left this caption alone on the
// grounds that it "asks for no judgement"; the op's own params say otherwise,
// and that call was made before anyone had rendered the screen.

import { FULL_SIZE_CHECK_LABEL } from "./loupe";

export interface HotPixelsPreviewInfo {
  hot_pixels_preview_skipped?: boolean;
}

// Returns the caption string when hot-pixel removal is skipped on this preview,
// or null otherwise (no hot-pixel op, or the preview is full-resolution).
export function hotPixelsSkippedCaption(
  info: HotPixelsPreviewInfo | undefined | null,
): string | null {
  if (!info || !info.hot_pixels_preview_skipped) return null;
  return (
    "Hot-pixel removal isn't shown on this downscaled preview — at preview scale "
    + "a real star looks just like a stray pixel, so previewing it would wrongly "
    + "erase stars. Your exported full-resolution image still gets the cleanup — "
    + `"${FULL_SIZE_CHECK_LABEL}" to see it, at the threshold you've set.`
  );
}
