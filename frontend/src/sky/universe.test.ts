import { describe, expect, it } from "vitest";
import type { SkyImage } from "./projection";
import {
  INNER_RADIUS, OUTER_RADIUS, radiusForDepth, scaleCaption, spanSummary,
  withPictures, type UniverseObject, type UniverseShell,
} from "./universe";

function obj(p: Partial<UniverseObject> & { safe: string }): UniverseObject {
  return {
    name: p.safe, object_id: "M1", object_name: "", type: "galaxy",
    ra_deg: 10, dec_deg: 20, distance_ly: 1000, distance_text: "1,000 ly",
    years_text: "1,000 years", depth: 0.5, ...p,
  };
}

function image(safe: string, extra: Partial<SkyImage> = {}): SkyImage {
  return {
    safe, name: safe, ra_deg: 10, dec_deg: 20, width_deg: 1.3, height_deg: 0.7,
    rotation_deg: 0, preview_url: `/api/${safe}.png`, timestamp_utc: null,
    run_id: 1, ...extra,
  };
}

describe("radiusForDepth", () => {
  it("spans the scene between the inner and outer radius", () => {
    expect(radiusForDepth(0)).toBe(INNER_RADIUS);
    expect(radiusForDepth(1)).toBe(OUTER_RADIUS);
    expect(radiusForDepth(0.5)).toBe((INNER_RADIUS + OUTER_RADIUS) / 2);
  });

  it("never puts an object on top of the camera's orbit centre", () => {
    // Depth 0 is the *scale's* inner bound, not the origin — an object there
    // would sit inside "you are here" and be unreadable.
    expect(radiusForDepth(0)).toBeGreaterThan(0);
  });

  it("clamps nonsense rather than throwing an object out of the scene", () => {
    expect(radiusForDepth(-3)).toBe(INNER_RADIUS);
    expect(radiusForDepth(9)).toBe(OUTER_RADIUS);
    expect(radiusForDepth(Number.NaN)).toBe(INNER_RADIUS);
  });
});

describe("withPictures", () => {
  it("joins each object to the picture of that target", () => {
    const joined = withPictures(
      [obj({ safe: "M_31" }), obj({ safe: "M_42" })],
      [image("M_42"), image("M_31")],
    );
    expect(joined.map((p) => p.object.safe)).toEqual(["M_31", "M_42"]);
    expect(joined[0].image?.preview_url).toBe("/api/M_31.png");
  });

  it("keeps an object that has no picture yet, as a bare marker", () => {
    const joined = withPictures([obj({ safe: "M_13" })], []);
    expect(joined).toHaveLength(1);
    expect(joined[0].image).toBeNull();
  });

  it("ignores a picture whose target isn't placed", () => {
    const joined = withPictures([obj({ safe: "M_13" })], [image("NGC_7000")]);
    expect(joined).toHaveLength(1);
    expect(joined[0].image).toBeNull();
  });
});

describe("scaleCaption", () => {
  const shells: UniverseShell[] = [
    { distance_ly: 1e3, depth: 0.1, label: "1,000 ly" },
    { distance_ly: 1e6, depth: 0.9, label: "1 million ly" },
  ];

  it("names the innermost and outermost rung", () => {
    expect(scaleCaption(shells)).toContain("1,000 ly");
    expect(scaleCaption(shells)).toContain("1 million ly");
  });

  it("says in plain words that the rings are not evenly spaced distances", () => {
    // A reader who assumes a linear axis misreads every gap on this map, so the
    // caption must say so without using the word "logarithmic".
    expect(scaleCaption(shells)).toContain("big step further");
    expect(scaleCaption(shells)).not.toContain("logarithmic");
  });

  it("says nothing when there is no scale worth describing", () => {
    expect(scaleCaption([])).toBe("");
    expect(scaleCaption([shells[0]])).toBe("");
  });
});

describe("spanSummary", () => {
  it("reads out the nearest and the furthest, which is the fact worth keeping", () => {
    const s = spanSummary([
      obj({ safe: "M_42", name: "M 42", distance_ly: 1344, distance_text: "1,340 ly" }),
      obj({ safe: "M_31", name: "M 31", distance_ly: 2.5e6, distance_text: "2.5 million ly" }),
    ]);
    expect(s).toBe("From M 42 at 1,340 ly out to M 31 at 2.5 million ly.");
  });

  it("doesn't claim a span for a single object", () => {
    const s = spanSummary([obj({ safe: "M_31", name: "M 31", distance_text: "2.5 million ly" })]);
    expect(s).toBe("M 31 sits 2.5 million ly away.");
  });

  it("is empty with nothing placed", () => {
    expect(spanSummary([])).toBe("");
  });
});
