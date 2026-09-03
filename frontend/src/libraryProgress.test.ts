import { describe, expect, it } from "vitest";
import type { TargetProgress } from "./api/client";
import {
  FINISH_FIRST_MAX_NIGHTS,
  describeLibraryProgress,
  finishFirstHint,
  nightsToGoLabel,
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
    recent_pace_s: over.recent_pace_s ?? null,
    field_fulls: over.field_fulls ?? null,
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

  it("scales a mosaic's per-type goal by its panel count when ranking", () => {
    // The canonical bug shape: 4 h totalled on a nebula (default 4 h goal)
    // reads as 'plenty' as a single field — that ranks it below every
    // in-progress row. On a 2×2 mosaic each panel is a quarter done, so the
    // scaled goal is 16 h and the row belongs *up* with the in-progress ones.
    const single = rankLibraryProgress([
      row({ safe: "S", object_type: "nebula", total_exposure_s: 4 * 3600 }),
    ]);
    expect(single[0].readiness.level).toBe("plenty");
    const mosaic = rankLibraryProgress([
      row({
        safe: "M",
        object_type: "nebula",
        total_exposure_s: 4 * 3600,
        field_fulls: 4,
      }),
    ]);
    expect(mosaic[0].readiness.level).not.toBe("plenty");
    expect(mosaic[0].readiness.goalHours).toBe(16);
    expect(mosaic[0].readiness.fieldFulls).toBe(4);
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

// --- "Finish this one first" (clear nights to go, from each target's own pace)

const H = 3600;

describe("rankLibraryProgress — nights to go", () => {
  it("divides the remaining gap by the target's own recent pace", () => {
    // Galaxy, 6 h goal, 4 h shot → 2 h to go at 1 h of kept subs per night.
    const [r] = rankLibraryProgress([
      row({
        safe: "A", object_type: "galaxy",
        total_exposure_s: 4 * H, recent_pace_s: 1 * H,
      }),
    ]);
    expect(r.nightsToGo).toBe(2);
  });

  it("rounds up — you cannot shoot 1.2 nights", () => {
    const [r] = rankLibraryProgress([
      row({
        safe: "A", object_type: "galaxy",
        total_exposure_s: 4 * H, recent_pace_s: 1.8 * H, // 2 h gap / 1.8 h
      }),
    ]);
    expect(r.nightsToGo).toBe(2);
  });

  it("says nothing without a pace (an older backend, or too little history)", () => {
    const [none] = rankLibraryProgress([
      row({ safe: "A", object_type: "galaxy", total_exposure_s: 4 * H }),
    ]);
    expect(none.nightsToGo).toBeNull();
    const [zero] = rankLibraryProgress([
      row({
        safe: "B", object_type: "galaxy",
        total_exposure_s: 4 * H, recent_pace_s: 0,
      }),
    ]);
    expect(zero.nightsToGo).toBeNull();
  });

  it("says nothing once a target already has plenty", () => {
    const [r] = rankLibraryProgress([
      row({
        safe: "A", object_type: "galaxy",
        total_exposure_s: 9 * H, recent_pace_s: 1 * H,
      }),
    ]);
    expect(r.readiness.level).toBe("plenty");
    expect(r.nightsToGo).toBeNull();
  });

  it("measures the gap against a user-set goal, not the per-type default", () => {
    const [r] = rankLibraryProgress([
      row({
        safe: "A", object_type: "galaxy", total_exposure_s: 4 * H,
        goal_s: 5 * H, recent_pace_s: 1 * H, // 1 h to go, not 2
      }),
    ]);
    expect(r.nightsToGo).toBe(1);
  });
});

describe("finishFirstHint", () => {
  it("names the target closest to done and how many nights it needs", () => {
    const ranked = rankLibraryProgress([
      row({
        safe: "NGC_7000", name: "NGC 7000", object_type: "nebula",
        total_exposure_s: 1 * H, recent_pace_s: 1 * H, // 3 h to go → 3 nights
      }),
      row({
        safe: "M_31", name: "M 31", object_type: "galaxy",
        total_exposure_s: 5.5 * H, recent_pace_s: 1 * H, // 0.5 h to go → 1 night
      }),
    ]);
    expect(finishFirstHint(ranked)).toBe(
      "Closest to done: M 31 — about 1 more clear night at your recent pace on it.",
    );
  });

  it("pluralises a multi-night answer", () => {
    const ranked = rankLibraryProgress([
      row({
        safe: "A", name: "A", object_type: "galaxy",
        total_exposure_s: 4 * H, recent_pace_s: 1 * H, // 2 nights
      }),
      row({
        safe: "B", name: "B", object_type: "galaxy",
        total_exposure_s: 1 * H, recent_pace_s: 1 * H, // 5 nights — past the cap
      }),
    ]);
    expect(finishFirstHint(ranked)).toContain("about 2 more clear nights");
  });

  it("stays silent when nothing is within reach — encouragement, never a scold", () => {
    const ranked = rankLibraryProgress([
      row({
        safe: "A", object_type: "galaxy",
        total_exposure_s: 1 * H, recent_pace_s: 1 * H, // 5 nights
      }),
      row({
        safe: "B", object_type: "galaxy",
        total_exposure_s: 0.5 * H, recent_pace_s: 1 * H, // 6 nights
      }),
    ]);
    expect(ranked.every((r) => (r.nightsToGo ?? 0) > FINISH_FIRST_MAX_NIGHTS)).toBe(true);
    expect(finishFirstHint(ranked)).toBeNull();
  });

  it("stays silent with only one target in progress (there is no 'first')", () => {
    const ranked = rankLibraryProgress([
      row({
        safe: "A", object_type: "galaxy",
        total_exposure_s: 5.5 * H, recent_pace_s: 1 * H,
      }),
      row({ safe: "B", object_type: "galaxy", total_exposure_s: 9 * H }), // plenty
    ]);
    expect(ranked[0].nightsToGo).toBe(1);
    expect(finishFirstHint(ranked)).toBeNull();
  });

  it("stays silent when no target has a measured pace", () => {
    const ranked = rankLibraryProgress([
      row({ safe: "A", object_type: "galaxy", total_exposure_s: 4 * H }),
      row({ safe: "B", object_type: "galaxy", total_exposure_s: 2 * H }),
    ]);
    expect(finishFirstHint(ranked)).toBeNull();
  });

  it("breaks a tie toward the target furthest along its goal", () => {
    const ranked = rankLibraryProgress([
      row({
        safe: "A", name: "A", object_type: "galaxy",
        total_exposure_s: 3 * H, recent_pace_s: 3 * H, // 3 h gap / 3 h → 1 night, 50%
      }),
      row({
        safe: "B", name: "B", object_type: "galaxy",
        total_exposure_s: 5.5 * H, recent_pace_s: 3 * H, // 0.5 h gap → 1 night, 92%
      }),
    ]);
    expect(finishFirstHint(ranked)).toContain("Closest to done: B");
  });

  it("is silent on an empty library", () => {
    expect(finishFirstHint([])).toBeNull();
  });
});

describe("nightsToGoLabel", () => {
  it("is a terse badge for a target within reach", () => {
    const [r] = rankLibraryProgress([
      row({
        safe: "A", object_type: "galaxy",
        total_exposure_s: 4 * H, recent_pace_s: 1 * H,
      }),
    ]);
    expect(nightsToGoLabel(r)).toBe("~2 more nights");
  });

  it("is singular for the last night", () => {
    const [r] = rankLibraryProgress([
      row({
        safe: "A", object_type: "galaxy",
        total_exposure_s: 5.5 * H, recent_pace_s: 1 * H,
      }),
    ]);
    expect(nightsToGoLabel(r)).toBe("~1 more night");
  });

  it("is absent past the cap, and with no pace", () => {
    const [far] = rankLibraryProgress([
      row({
        safe: "A", object_type: "galaxy",
        total_exposure_s: 1 * H, recent_pace_s: 1 * H, // 5 nights
      }),
    ]);
    expect(nightsToGoLabel(far)).toBeNull();
    const [none] = rankLibraryProgress([
      row({ safe: "B", object_type: "galaxy", total_exposure_s: 4 * H }),
    ]);
    expect(nightsToGoLabel(none)).toBeNull();
  });
});
