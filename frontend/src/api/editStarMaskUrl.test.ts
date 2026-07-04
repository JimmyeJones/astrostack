import { describe, expect, it } from "vitest";
import { api } from "./client";
import type { Recipe } from "./client";

describe("editStarMaskUrl", () => {
  const recipe: Recipe = { ops: [], base_run_id: 3, version: 1 };

  it("omits all optional params when none are given", () => {
    expect(api.editStarMaskUrl("M_1", 3)).toBe(
      "/api/targets/M_1/stack-runs/3/editor/star-mask",
    );
  });

  it("includes size_px, recipe, and uid when provided", () => {
    const url = api.editStarMaskUrl("M_1", 3, 8, recipe, "star-uid");
    expect(url).toContain("size_px=8");
    expect(url).toMatch(/[?&]recipe=/);
    expect(url).toContain("uid=star-uid");
  });

  it("still passes the recipe when no star op (size/uid) is selected", () => {
    const url = api.editStarMaskUrl("M_1", 3, undefined, recipe, undefined);
    expect(url).not.toContain("size_px");
    expect(url).not.toContain("uid=");
    expect(url).toMatch(/[?&]recipe=/);
  });
});
