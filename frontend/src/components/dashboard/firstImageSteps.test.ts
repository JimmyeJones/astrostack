import { describe, expect, it } from "vitest";
import type { DashboardStats, SystemInfo } from "../../api/client";
import {
  firstImageComplete, firstImageNextStep, firstImageSteps,
} from "./firstImageSteps";

function sys(over: Partial<SystemInfo["astap"]> = {}): SystemInfo {
  return {
    version: "0.0.0", data_root: "/data", cpu_count: 4, cpu_workers: 3,
    gpu_available: false, disk: {}, memory: {}, watcher_enabled: true,
    astap: { found: true, path: "/usr/bin/astap", star_db_found: true, ...over },
  };
}

function stats(over: Partial<DashboardStats> = {}): DashboardStats {
  return {
    n_targets: 0, n_frames: 0, n_frames_accepted: 0, total_exposure_s: 0,
    integration_hours: 0, acceptance_rate: null, n_stack_runs: 0,
    n_targets_with_stacks: 0, active_jobs: 0, recent_stacks: [], disk: {},
    ...over,
  };
}

describe("firstImageSteps", () => {
  it("walks the journey in the order a beginner does it", () => {
    expect(firstImageSteps(sys(), stats()).map((s) => s.key))
      .toEqual(["frames", "solve", "checked", "stack"]);
  });

  it("leaves every step open on a brand-new install", () => {
    const steps = firstImageSteps(sys({ found: false }), stats());
    expect(steps.every((s) => !s.done)).toBe(true);
    expect(firstImageComplete(steps)).toBe(false);
    expect(firstImageNextStep(steps)?.key).toBe("frames");
  });

  it("ticks each step off from the signals the Dashboard already has", () => {
    const steps = firstImageSteps(
      sys(), stats({ n_frames: 40, n_frames_accepted: 32, n_stack_runs: 1 }));
    expect(steps.map((s) => s.done)).toEqual([true, true, true, true]);
    expect(firstImageComplete(steps)).toBe(true);
    expect(firstImageNextStep(steps)).toBeNull();
  });

  it("points at the first thing still to do, mid-journey", () => {
    const steps = firstImageSteps(sys(), stats({ n_frames: 40, n_frames_accepted: 32 }));
    expect(firstImageNextStep(steps)?.key).toBe("stack");
    expect(firstImageComplete(steps)).toBe(false);
  });

  it("counts solving as not-ready when ASTAP is missing", () => {
    const steps = firstImageSteps(sys({ found: false }), stats({ n_frames: 5 }));
    expect(steps.find((s) => s.key === "solve")?.done).toBe(false);
    expect(firstImageNextStep(steps)?.key).toBe("solve");
  });

  it("counts solving as not-ready when the star database is missing", () => {
    const steps = firstImageSteps(sys({ star_db_found: false }), stats({ n_frames: 5 }));
    expect(steps.find((s) => s.key === "solve")?.done).toBe(false);
  });

  it("doesn't hold an unreported star database against an ASTAP that runs", () => {
    // Some builds don't report the database; only an explicit `false` counts
    // against it — the same one-sided rule the readiness banner uses.
    const steps = firstImageSteps(
      sys({ star_db_found: undefined }), stats({ n_frames: 5 }));
    expect(steps.find((s) => s.key === "solve")?.done).toBe(true);
  });

  it("treats missing data as 'not done', never as progress it can't see", () => {
    const steps = firstImageSteps(undefined, undefined);
    expect(steps.every((s) => !s.done)).toBe(true);
  });

  it("gives every step a plain sentence, a hint and somewhere to go", () => {
    for (const s of firstImageSteps(sys(), stats())) {
      expect(s.label.length).toBeGreaterThan(10);
      expect(s.hint.length).toBeGreaterThan(20);
      expect(s.href.startsWith("/")).toBe(true);
      expect(s.action.length).toBeGreaterThan(3);
    }
  });
});
