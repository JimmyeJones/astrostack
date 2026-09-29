import { describe, expect, it } from "vitest";
import { exampleLead, hasRenderableExamples } from "./rejectExamples";

describe("exampleLead", () => {
  it("says what to look for, per cause", () => {
    expect(exampleLead("trailed", 3)).toContain("straight bright line");
    expect(exampleLead("clouds", 3)).toContain("far fewer stars");
    expect(exampleLead("soft", 3)).toContain("fat and fuzzy");
  });

  it("reassures where the cause is the weather, not the setup", () => {
    expect(exampleLead("clouds", 2)).toContain("Nothing was wrong with your setup");
  });

  it("counts in words a person uses", () => {
    expect(exampleLead("soft", 1)).toContain("Here's one we set aside");
    expect(exampleLead("soft", 3)).toContain("Here are 3 we set aside");
  });

  it("stays silent for a bucket with no copy, and for an empty strip", () => {
    // The backend only sends examples for causes you can see; a bucket that
    // arrived without copy here was added on one side only, and thumbnails with
    // nothing saying what they show are a puzzle, not a lesson.
    expect(exampleLead("removed", 3)).toBeNull();
    expect(exampleLead("unsolved", 3)).toBeNull();
    expect(exampleLead("soft", 0)).toBeNull();
  });
});

describe("hasRenderableExamples", () => {
  it("is false for an older backend and for nothing worth showing", () => {
    expect(hasRenderableExamples(undefined)).toBe(false);
    expect(hasRenderableExamples({})).toBe(false);
    expect(hasRenderableExamples({ soft: [] })).toBe(false);
    expect(hasRenderableExamples({ removed: [{ frame_id: 1, name: "a" }] }))
      .toBe(false);
  });

  it("is true as soon as one bucket can render", () => {
    expect(hasRenderableExamples({
      removed: [{ frame_id: 1, name: "a" }],
      soft: [{ frame_id: 2, name: "b" }],
    })).toBe(true);
  });
});
