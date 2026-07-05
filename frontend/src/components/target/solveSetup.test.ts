import { describe, it, expect } from "vitest";
import { detectSolveSetupProblem } from "./solveSetup";

describe("detectSolveSetupProblem", () => {
  it("returns null when nothing is rejected", () => {
    expect(detectSolveSetupProblem({})).toBeNull();
    expect(detectSolveSetupProblem(undefined)).toBeNull();
    expect(detectSolveSetupProblem(null)).toBeNull();
  });

  it("ignores ordinary per-frame reject reasons", () => {
    expect(detectSolveSetupProblem({ "qc:fwhm": 3, "auto:streak": 1, user: 2 })).toBeNull();
  });

  it("ignores a solve failure that isn't a setup problem (no solution)", () => {
    // A frame that simply couldn't be solved (few stars) is normal, not a
    // missing-ASTAP/database blocker.
    expect(detectSolveSetupProblem({ "solve_failed:no solution": 2 })).toBeNull();
  });

  it("does NOT treat a single 'could not open' as a setup problem", () => {
    // Could be one corrupt frame; must not nag the user to reinstall ASTAP.
    expect(detectSolveSetupProblem({ "solve_failed:could not open file": 1 })).toBeNull();
  });

  it("flags a missing/misconfigured ASTAP binary", () => {
    // The engine's installer hint: "astap.exe not found. Install ASTAP from ..."
    const counts = {
      "solve_failed:astap.exe not found. Install ASTAP from https://www.hnsky.org/astap.htm and ":
        7,
    };
    expect(detectSolveSetupProblem(counts)).toEqual({ kind: "astap", frames: 7 });
  });

  it("flags a missing star database", () => {
    expect(
      detectSolveSetupProblem({ "solve_failed:Error: no star database found": 5 }),
    ).toEqual({ kind: "database", frames: 5 });
  });

  it("prefers the ASTAP-missing verdict and sums matching frame counts", () => {
    const counts = {
      "solve_failed:astap.exe not found. Install ASTAP": 4,
      "solve_failed:no star database found": 2,
      "qc:fwhm": 1,
    };
    // ASTAP-missing is more fundamental; only its own frames are counted.
    expect(detectSolveSetupProblem(counts)).toEqual({ kind: "astap", frames: 4 });
  });

  it("is case-insensitive", () => {
    expect(
      detectSolveSetupProblem({ "solve_failed:No Star Database Found": 3 }),
    ).toEqual({ kind: "database", frames: 3 });
  });
});
