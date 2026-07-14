import { describe, expect, it } from "vitest";
import type { TargetProgress } from "./api/client";
import {
  describeLibraryProgress,
  objectTypeLabel,
  rankLibraryProgress,
} from "./libraryProgress";

function row(over: Partial<TargetProgress> & { safe: string }): TargetProgress {
  return {
    safe: over.safe,
    name: over.name ?? over.safe,
    total_exposure_s: over.total_exposure_s ?? 0,
    object_type: over.object_type ?? null,
    goal_s: over.goal_s ?? null,
  };
}

describe("rankLibraryProgress", () => {
  it("drops targets with no integration", () => {
    const ranked = rankLibraryProgress([row({ safe: "A", total_exposure_s: 0 })]);
    expect(ranked).toHaveLength(0);
  });

  it("puts in-progress targets before ones with plenty, nearest-to-goal first", () => {
    // All galaxies (6 h goal): B is nearly there, A just started, C is done.
    const ranked = rankLibraryProgress([
      row({ safe: "A", object_type: "galaxy", total_exposure_s: 0.5 * 3600 }), // ~8%
      row({ safe: "B", object_type: "galaxy", total_exposure_s: 5 * 3600 }), // ~83% (close)
      row({ safe: "C", object_type: "galaxy", total_exposure_s: 9 * 3600 }), // plenty
    ]);
    expect(ranked.map((r) => r.row.safe)).toEqual(["B", "A", "C"]);
    expect(ranked[2].readiness.level).toBe("plenty");
  });

  it("honours a user-set goal override when ranking", () => {
    // Same 2 h of a galaxy: with the default 6 h goal it's 'solid'; with a
    // user goal of 2 h it's 'plenty' and sinks below an in-progress sibling.
    const withDefault = rankLibraryProgress([
      row({ safe: "G", object_type: "galaxy", total_exposure_s: 2 * 3600 }),
    ]);
    expect(withDefault[0].readiness.level).toBe("solid");
    const withGoal = rankLibraryProgress([
      row({ safe: "G", object_type: "galaxy", total_exposure_s: 2 * 3600, goal_s: 2 * 3600 }),
    ]);
    expect(withGoal[0].readiness.level).toBe("plenty");
    expect(withGoal[0].readiness.customGoal).toBe(true);
  });
});

describe("objectTypeLabel", () => {
  it("gives a friendly word for a recognised bucket", () => {
    expect(objectTypeLabel("Galaxy")).toBe("galaxy");
    expect(objectTypeLabel("Nebula")).toBe("nebula");
    expect(objectTypeLabel("Cluster")).toBe("cluster");
  });

  it("returns null for the unknown/other bucket (no meaningless label)", () => {
    expect(objectTypeLabel("Other")).toBeNull();
  });
});

describe("describeLibraryProgress", () => {
  it("is empty for no targets", () => {
    expect(describeLibraryProgress([])).toBe("");
  });

  it("summarises a mix of in-progress and finished targets", () => {
    const ranked = rankLibraryProgress([
      row({ safe: "A", object_type: "galaxy", total_exposure_s: 1 * 3600 }),
      row({ safe: "B", object_type: "galaxy", total_exposure_s: 2 * 3600 }),
      row({ safe: "C", object_type: "cluster", total_exposure_s: 3 * 3600 }), // 1.5 h goal → plenty
    ]);
    expect(describeLibraryProgress(ranked)).toBe(
      "2 targets could use more time; 1 has plenty for a clean image.",
    );
  });

  it("reads naturally when everything still needs time", () => {
    const ranked = rankLibraryProgress([
      row({ safe: "A", object_type: "galaxy", total_exposure_s: 1 * 3600 }),
    ]);
    expect(describeLibraryProgress(ranked)).toBe(
      "1 target is in progress — keep shooting to reach a clean image.",
    );
  });

  it("reads naturally when everything has plenty", () => {
    const ranked = rankLibraryProgress([
      row({ safe: "A", object_type: "cluster", total_exposure_s: 3 * 3600 }),
      row({ safe: "B", object_type: "cluster", total_exposure_s: 4 * 3600 }),
    ]);
    expect(describeLibraryProgress(ranked)).toBe(
      "All 2 targets have plenty of integration for a clean image.",
    );
  });
});
