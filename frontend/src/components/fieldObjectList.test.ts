import { describe, expect, it } from "vitest";

import type { FieldObject } from "../api/client";
import { describeFieldObjects } from "./fieldObjectList";

function obj(overrides: Partial<FieldObject>): FieldObject {
  return {
    catalog_id: "M42",
    name: "Orion Nebula",
    type: "nebula",
    ra_deg: 83.8,
    dec_deg: -5.4,
    x_px: 500,
    y_px: 500,
    ...overrides,
  };
}

describe("describeFieldObjects", () => {
  it("labels a named object with its designation and a friendly type clause", () => {
    const [d] = describeFieldObjects([obj({ x_px: 500, y_px: 500 })], 1000, 1000);
    expect(d.label).toBe("Orion Nebula (M42)");
    expect(d.typePhrase).toBe("a nebula"); // consonant → "a"
    expect(d.positionPhrase).toBe("near the centre");
  });

  it("uses 'an' before a vowel-initial type and a bare id when there's no name", () => {
    const [d] = describeFieldObjects(
      [obj({ catalog_id: "NGC 869", name: "", type: "open cluster", x_px: 500, y_px: 500 })],
      1000, 1000,
    );
    expect(d.label).toBe("NGC 869");
    expect(d.typePhrase).toBe("an open cluster"); // vowel → "an"
  });

  it("drops the type clause when the catalog type is empty", () => {
    const [d] = describeFieldObjects([obj({ type: "" })], 1000, 1000);
    expect(d.typePhrase).toBe("");
  });

  it("names the corner an off-centre object sits in", () => {
    // Top-left of the frame: small x (left) and small y (top, since y runs down).
    const [tl] = describeFieldObjects([obj({ x_px: 100, y_px: 100 })], 1000, 1000);
    expect(tl.positionPhrase).toBe("toward the top-left");
    // Bottom-right: large x, large y.
    const [br] = describeFieldObjects([obj({ x_px: 900, y_px: 900 })], 1000, 1000);
    expect(br.positionPhrase).toBe("toward the bottom-right");
    // Straight up: centred x, small y.
    const [top] = describeFieldObjects([obj({ x_px: 500, y_px: 60 })], 1000, 1000);
    expect(top.positionPhrase).toBe("toward the top");
  });

  it("orders nearest-the-centre first and caps the list at the limit", () => {
    const objs = [
      obj({ catalog_id: "FAR", x_px: 980, y_px: 980 }),
      obj({ catalog_id: "MID", x_px: 700, y_px: 700 }),
      obj({ catalog_id: "NEAR", x_px: 520, y_px: 520 }),
    ];
    const all = describeFieldObjects(objs, 1000, 1000);
    expect(all.map((d) => d.catalogId)).toEqual(["NEAR", "MID", "FAR"]);
    const capped = describeFieldObjects(objs, 1000, 1000, 2);
    expect(capped.map((d) => d.catalogId)).toEqual(["NEAR", "MID"]);
  });

  it("returns [] for no objects or a degenerate grid", () => {
    expect(describeFieldObjects([], 1000, 1000)).toEqual([]);
    expect(describeFieldObjects([obj({})], 0, 0)).toEqual([]);
  });

  it("always yields a non-empty position phrase for an off-centre near-diagonal", () => {
    // r ≥ centre radius but neither axis past its threshold → the fallback picks
    // the stronger axis rather than falling through to an empty phrase.
    const [d] = describeFieldObjects([obj({ x_px: 660, y_px: 655 })], 1000, 1000);
    expect(d.positionPhrase).not.toBe("");
    expect(d.positionPhrase).toBe("toward the right");
  });
});
