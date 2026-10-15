import { describe, expect, it } from "vitest";
import {
  FRAME_TILES, PICKY_LEVELS, pickyLevel, pickyPatch, pickyWaitingNote, tileLeftOut, trailNote,
  type PickyLevelId,
} from "./framePicky";

describe("How picky? — the four levels over two fields", () => {
  it("maps each level onto auto_grade_frames + auto_grade_sensitivity as the spec says", () => {
    expect(pickyPatch("gentle")).toEqual({ auto_grade_frames: true, auto_grade_sensitivity: "conservative" });
    expect(pickyPatch("balanced")).toEqual({ auto_grade_frames: true, auto_grade_sensitivity: "balanced" });
    expect(pickyPatch("strict")).toEqual({ auto_grade_frames: true, auto_grade_sensitivity: "aggressive" });
  });

  it("Keep all only switches grading off — the stored sensitivity is left alone", () => {
    expect(pickyPatch("off")).toEqual({ auto_grade_frames: false });
  });

  it("reads grading off as Keep all, whatever sensitivity is stored", () => {
    expect(pickyLevel({})).toBe("off");
    expect(pickyLevel({ auto_grade_frames: false, auto_grade_sensitivity: "aggressive" })).toBe("off");
  });

  it("reads each stored sensitivity back as its level (a missing one is the field's default)", () => {
    expect(pickyLevel({ auto_grade_frames: true })).toBe("balanced");
    expect(pickyLevel({ auto_grade_frames: true, auto_grade_sensitivity: "conservative" })).toBe("gentle");
    expect(pickyLevel({ auto_grade_frames: true, auto_grade_sensitivity: "aggressive" })).toBe("strict");
  });

  it("picks no button rather than a wrong one for a sensitivity it doesn't know", () => {
    expect(pickyLevel({ auto_grade_frames: true, auto_grade_sensitivity: "extreme" })).toBeNull();
  });

  it("round-trips: every level reads back as itself", () => {
    for (const l of PICKY_LEVELS) expect(pickyLevel(pickyPatch(l.id))).toBe(l.id);
  });

  it("never claims a level judges only one kind of fault — every level grades every measure", () => {
    // grading.py moves one z threshold per level over all five metrics, so a
    // note naming a single kind ("only clouded-out frames") would be false.
    for (const l of PICKY_LEVELS) expect(l.note).not.toMatch(/\bonly\s+cloud/i);
  });
});

describe("the frame illustration", () => {
  const leftOut = (level: PickyLevelId | null, keepTrails = false) =>
    FRAME_TILES.filter((t) => tileLeftOut(t, level, keepTrails)).map((t) => t.kind);

  it("leaves more out at each stricter level, never fewer", () => {
    const order: PickyLevelId[] = ["off", "gentle", "balanced", "strict"];
    for (let i = 1; i < order.length; i++) {
      const before = new Set(leftOut(order[i - 1]));
      const after = new Set(leftOut(order[i]));
      for (const k of before) expect(after.has(k)).toBe(true);
      expect(after.size).toBeGreaterThan(before.size);
    }
  });

  it("Keep all leaves out only the trail, and only while trails aren't kept", () => {
    expect(leftOut("off", false)).toEqual(["trail"]);
    expect(leftOut("off", true)).toEqual([]);
  });

  it("never leaves out a sharp or a merely 'a bit soft' frame — not even on Strict", () => {
    // The grader's "meaningfully worse" floors (≥25 % softer, …) don't move
    // with the level, so a small difference is never cut.
    const strict = leftOut("strict", true);
    expect(strict).not.toContain("sharp");
    expect(strict).not.toContain("bitsoft");
    expect(FRAME_TILES.filter((t) => t.kind === "sharp").length).toBeGreaterThanOrEqual(4);
  });

  it("decides the trail by the trails switch alone, at every level", () => {
    const trail = FRAME_TILES.find((t) => t.kind === "trail")!;
    for (const l of PICKY_LEVELS) {
      expect(tileLeftOut(trail, l.id, false)).toBe(true);
      expect(tileLeftOut(trail, l.id, true)).toBe(false);
    }
  });

  it("draws the twelve tiles the spec asks for", () => {
    expect(FRAME_TILES).toHaveLength(12);
  });
});

describe("the notes under the control", () => {
  it("says, while grading is on and Check is off, that arriving frames aren't sorted out", () => {
    expect(pickyWaitingNote({ auto_grade_frames: true, auto_qc: false })).toMatch(/Check \(step 3\) is off/);
    expect(pickyWaitingNote({ auto_grade_frames: true, auto_qc: true })).toBeNull();
    expect(pickyWaitingNote({ auto_grade_frames: false, auto_qc: false })).toBeNull();
  });

  it("explains the trails switch in both positions", () => {
    expect(trailNote(false)).toMatch(/^Off \(recommended\)/);
    expect(trailNote(true)).toMatch(/^On: a frame with a trail is kept/);
  });
});
