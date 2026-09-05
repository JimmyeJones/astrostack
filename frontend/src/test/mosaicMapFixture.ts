// One mosaic-map fixture for the three surfaces that read one, so a change to
// the shape is a change in one place. Deliberately a plain module rather than an
// export from a `.test.ts`: importing a test file registers its suites in the
// importing file too, which silently runs the same assertions twice.

import type { MosaicDepthMap } from "../api/client";

function panel(row: number, col: number, subs: number) {
  return { row, col, n_frames: subs, exposure_s: subs * 10, ra_deg: 10, dec_deg: 41 };
}

/** A 2×2 mosaic whose bottom-right corner is a tenth of the others — the shape
 *  the engine's own `aim_hint` tests use, with the clause it produces for it. */
export function mosaicMap(overrides: Partial<MosaicDepthMap> = {}): MosaicDepthMap {
  return {
    panels: [panel(0, 0, 120), panel(0, 1, 120), panel(1, 0, 120), panel(1, 1, 12)],
    rows: 2, cols: 2, median_exposure_s: 1200,
    thin: panel(1, 1, 12),
    text: "Your 2×2 mosaic is thinnest at the bottom-right: about 2 min there "
      + "against 20 min on a typical panel. That part of the picture will look "
      + "grainier than the rest until it catches up — more time on this mosaic "
      + "is what evens it out.",
    aim_hint: "Thinnest at the bottom-right: about 2 min there against 20 min "
      + "on a typical panel.",
    ...overrides,
  };
}
