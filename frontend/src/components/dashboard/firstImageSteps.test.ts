import { describe, expect, it } from "vitest";
import type { DashboardStats, SystemInfo } from "../../api/client";
import {
  firstImageComplete, firstImageDone, firstImageDoneMessage, firstImageHasPicture,
  firstImageNextStep, firstImageSteps,
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
      .toEqual(["frames", "solve", "checked", "stack", "edit", "export"]);
  });

  it("leaves every step open on a brand-new install", () => {
    const steps = firstImageSteps(sys({ found: false }), stats());
    expect(steps.every((s) => !s.done)).toBe(true);
    expect(firstImageComplete(steps)).toBe(false);
    expect(firstImageNextStep(steps)?.key).toBe("frames");
  });

  it("ticks each step off from the signals the Dashboard already has", () => {
    const steps = firstImageSteps(sys(), stats({
      n_frames: 40, n_frames_accepted: 32, n_stack_runs: 1,
      n_edited_runs: 1, n_exported_runs: 1,
    }));
    expect(steps.map((s) => s.done)).toEqual([true, true, true, true, true, true]);
    expect(firstImageComplete(steps)).toBe(true);
    expect(firstImageNextStep(steps)).toBeNull();
  });

  it("sends a fresh stack to the editor, then to Export — the half of the "
    + "journey the card used to only mention", () => {
    // A first stack is linear and dark on purpose. Before this the card
    // congratulated at that point and retired, so the one thing a beginner most
    // needs to be told next — press Auto, then Export — was a sentence in a
    // well-done rather than a step with a link.
    const stacked = stats({ n_frames: 40, n_frames_accepted: 32, n_stack_runs: 1 });
    expect(firstImageNextStep(firstImageSteps(sys(), stacked))?.key).toBe("edit");
    expect(firstImageComplete(firstImageSteps(sys(), stacked))).toBe(false);

    const edited = stats({ ...stacked, n_edited_runs: 2 });
    expect(firstImageNextStep(firstImageSteps(sys(), edited))?.key).toBe("export");

    const exported = stats({ ...edited, n_exported_runs: 1 });
    expect(firstImageNextStep(firstImageSteps(sys(), exported))).toBeNull();
  });

  it("reads an older backend's missing edit/export counts as not done", () => {
    // Additive fields: a backend from before them sends neither, and the safe
    // reading is "that step is still to do" — never a tick the app can't see.
    const st = stats({ n_frames: 40, n_frames_accepted: 32, n_stack_runs: 1 });
    delete (st as { n_edited_runs?: number }).n_edited_runs;
    delete (st as { n_exported_runs?: number }).n_exported_runs;
    const steps = firstImageSteps(sys(), st);
    expect(steps.find((s) => s.key === "edit")?.done).toBe(false);
    expect(steps.find((s) => s.key === "export")?.done).toBe(false);
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

  it("labels the solve step as the setup it actually measures", () => {
    // The tick reads whether ASTAP is installed, never whether your frames got
    // solved — and the two come apart on the app's own first-run path: the
    // bundled sample ships pre-solved, so pressing "Stack it" with no ASTAP
    // gives a finished picture beside a card reading "3 of 4 done" with this
    // step unticked. A label promising something about *your frames* made that
    // read as a contradiction; one naming the setup does not.
    const steps = firstImageSteps(sys({ found: false }),
      stats({ n_frames: 6, n_frames_accepted: 6, n_stack_runs: 1 }));
    const solve = steps.find((s) => s.key === "solve");
    expect(solve?.done).toBe(false);
    expect(solve?.label).toBe("Set up plate solving (ASTAP)");
    // The sample's own journey, exactly as the dogfood run found it: everything
    // but the setup ticked, and the card leading with the setup.
    expect(steps.map((s) => s.done)).toEqual([true, false, true, true, false, false]);
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

describe("firstImageDone", () => {
  it("counts a stacked Moon/Sun still as a finished picture", () => {
    // The bug this exists for: a video ingests no FITS, solves nothing and
    // creates no stack run, so every step is open — yet there is a picture.
    const st = stats({ n_video_stills: 1 });
    const steps = firstImageSteps(sys({ found: false }), st);
    expect(steps.every((s) => !s.done)).toBe(true);
    expect(firstImageComplete(steps)).toBe(false);
    expect(firstImageDone(steps, st)).toBe(true);
  });

  it("never ticks a deep-sky step off a video", () => {
    // Only the outcome recognises a still — the steps are still the right
    // advice, and claiming frames were ingested or solved would be a lie.
    const steps = firstImageSteps(sys(), stats({ n_video_stills: 3 }));
    expect(steps.map((s) => s.done))
      .toEqual([false, true, false, false, false, false]);
    expect(firstImageNextStep(steps)?.key).toBe("frames");
  });

  it("agrees with every step when there is no still", () => {
    const none = stats();
    expect(firstImageDone(firstImageSteps(sys(), none), none)).toBe(false);
    const all = stats({
      n_frames: 40, n_frames_accepted: 32, n_stack_runs: 1,
      n_edited_runs: 1, n_exported_runs: 1,
    });
    expect(firstImageDone(firstImageSteps(sys(), all), all)).toBe(true);
  });

  it("reads an older backend's missing count as no stills", () => {
    const st = stats();
    delete (st as { n_video_stills?: number }).n_video_stills;
    expect(firstImageDone(firstImageSteps(sys(), st), st)).toBe(false);
    expect(firstImageDone(firstImageSteps(sys(), undefined), undefined)).toBe(false);
  });

  it("words the well-done for how they actually got there", () => {
    const video = stats({ n_video_stills: 1 });
    const msg = firstImageDoneMessage(firstImageSteps(sys(), video));
    // Pointing a Moon-video user at the deep-sky editor would be wrong.
    expect(msg).toContain("Gallery");
    expect(msg).not.toContain("editor");
    // ...and it must not quote a step count it no longer has ("the same four
    // steps below" outlived the four steps).
    expect(msg).not.toContain("four steps");

    const deep = stats({
      n_frames: 40, n_frames_accepted: 32, n_stack_runs: 1,
      n_edited_runs: 1, n_exported_runs: 1,
    });
    const done = firstImageDoneMessage(firstImageSteps(sys(), deep));
    // The finishing steps are now ticked boxes, so the congratulation says the
    // journey is over rather than handing out two more instructions.
    expect(done).toContain("whole journey");
    expect(done).not.toContain("Open it");
  });
});

describe("firstImageHasPicture", () => {
  it("is the first-picture steps only — blind to the two finishing steps", () => {
    // The predicate that keeps the card off an established install. Reading the
    // editor steps here would make a box with 300 stacks and no exported edit
    // look like a beginner mid-journey, and the card would appear for the first
    // time on an upgrade — exactly what the STARTED flag exists to prevent.
    const stacked = stats({ n_frames: 40, n_frames_accepted: 32, n_stack_runs: 1 });
    const steps = firstImageSteps(sys(), stacked);
    expect(firstImageComplete(steps)).toBe(false);
    expect(firstImageHasPicture(steps, stacked)).toBe(true);
  });

  it("is false before the first stack, and true off a Moon/Sun still", () => {
    const nothing = stats({ n_frames: 40, n_frames_accepted: 32 });
    expect(firstImageHasPicture(firstImageSteps(sys(), nothing), nothing)).toBe(false);
    const video = stats({ n_video_stills: 1 });
    expect(firstImageHasPicture(firstImageSteps(sys(), video), video)).toBe(true);
  });
});
