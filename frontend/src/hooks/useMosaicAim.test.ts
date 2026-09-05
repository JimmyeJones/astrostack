import { describe, expect, it } from "vitest";

import { mosaicAimLine } from "./useMosaicAim";
import { mosaicMap } from "../test/mosaicMapFixture";

describe("mosaicAimLine", () => {
  it("passes the backend's clause through when a panel is behind", () => {
    expect(mosaicAimLine(mosaicMap()))
      .toBe("Thinnest at the bottom-right: about 2 min there against 20 min "
        + "on a typical panel.");
  });

  it("says nothing for a single field, an even mosaic, or an older backend", () => {
    expect(mosaicAimLine(null)).toBeNull();          // not a mosaic
    expect(mosaicAimLine(undefined)).toBeNull();     // request failed / still pending
    // An even mosaic: the long sentence still reassures, but there is no corner
    // to aim at, so a recommendation card shows exactly what it shows today.
    expect(mosaicAimLine(mosaicMap({ thin: null, aim_hint: null }))).toBeNull();
    // A backend too old to send the clause must not be papered over locally —
    // the wording lives in the engine so every surface quotes one sentence.
    const old = mosaicMap();
    delete (old as { aim_hint?: unknown }).aim_hint;
    expect(mosaicAimLine(old)).toBeNull();
    // Whitespace is not a sentence.
    expect(mosaicAimLine(mosaicMap({ aim_hint: "   " }))).toBeNull();
  });
});
