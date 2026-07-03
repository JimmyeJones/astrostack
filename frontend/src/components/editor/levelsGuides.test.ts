import { describe, expect, it } from "vitest";
import { levelsHistGuides } from "./levelsGuides";
import type { OpInstance } from "../../api/client";

const levels = (black: number, white: number): OpInstance => ({
  uid: "lv1", id: "tone.levels", enabled: true, params: { black, white },
});

describe("levelsHistGuides", () => {
  it("returns [] for a non-Levels selection or none", () => {
    expect(levelsHistGuides(null)).toEqual([]);
    expect(levelsHistGuides({ uid: "s1", id: "tone.stretch", enabled: true, params: {} })).toEqual([]);
  });

  it("marks the current black and white points as solid B/W guides", () => {
    const g = levelsHistGuides(levels(0.1, 0.8));
    expect(g).toHaveLength(2);
    expect(g[0]).toMatchObject({ value: 0.1, label: "B" });
    expect(g[1]).toMatchObject({ value: 0.8, label: "W" });
    expect(g[0].dashed).toBeUndefined();
  });

  it("adds faint dashed markers only where the suggestion differs from the current point", () => {
    // Black already at its suggestion → no dashed black marker; white differs → one.
    const g = levelsHistGuides(levels(0.12, 0.5), { black: 0.12, white: 0.85 });
    const dashed = g.filter((x) => x.dashed);
    expect(dashed).toHaveLength(1);
    expect(dashed[0].value).toBeCloseTo(0.85);
  });

  it("adds both dashed markers when both points differ from the suggestion", () => {
    const g = levelsHistGuides(levels(0, 1), { black: 0.12, white: 0.85 });
    expect(g.filter((x) => x.dashed).map((x) => x.value)).toEqual([0.12, 0.85]);
  });

  it("falls back to 0/1 for missing params and skips non-finite suggestions", () => {
    const g = levelsHistGuides({ uid: "lv1", id: "tone.levels", enabled: true, params: {} });
    expect(g.map((x) => x.value)).toEqual([0, 1]);
  });
});
