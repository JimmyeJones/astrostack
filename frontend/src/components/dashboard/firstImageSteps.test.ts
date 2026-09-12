import { describe, expect, it } from "vitest";
import type { DashboardStats, SystemInfo } from "../../api/client";
import {
  firstImageComplete, firstImageDone, firstImageDoneMessage, firstImageHasPicture,
  firstImageLeadText, firstImageNextStep, firstImageSkippedSteps, firstImageSteps,
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
      n_edited_runs: 1, n_finished_pictures: 1,
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

    const exported = stats({ ...edited, n_finished_pictures: 1 });
    expect(firstImageNextStep(firstImageSteps(sys(), exported))).toBeNull();
  });

  it("never leaves an earlier step open under a later one that is done", () => {
    // Export without ever pressing Save: the export marker exists and no recipe
    // does. Reading the recipe alone would tick "Save your edited version" while
    // "Finish it in the editor" above it stayed open, which reads as a bug.
    const steps = firstImageSteps(sys(), stats({
      n_frames: 40, n_frames_accepted: 32, n_stack_runs: 1, n_finished_pictures: 1,
    }));
    expect(steps.map((s) => s.done)).toEqual([true, true, true, true, true, true]);
    expect(firstImageComplete(steps)).toBe(true);
  });

  it("reads an older backend's missing edit/export counts as not done", () => {
    // Additive fields: a backend from before them sends neither, and the safe
    // reading is "that step is still to do" — never a tick the app can't see.
    const st = stats({ n_frames: 40, n_frames_accepted: 32, n_stack_runs: 1 });
    delete (st as { n_edited_runs?: number }).n_edited_runs;
    delete (st as { n_finished_pictures?: number }).n_finished_pictures;
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
    // up to the stack ticked, with the setup step skipped over.
    expect(steps.map((s) => s.done)).toEqual([true, false, true, true, false, false]);
    // "Next" is what is *ahead* of them — the editor — not the setup step they
    // already overtook. (This assertion used to read "solve"; it was pinning the
    // behaviour the 2026-09-12 dogfood pass photographed as wrong, not a
    // property worth keeping. The setup step is still listed, still unticked and
    // still linked below, and `firstImageSkippedSteps` names it.)
    expect(firstImageNextStep(steps)?.key).toBe("edit");
    expect(firstImageSkippedSteps(steps).map((s) => s.key)).toEqual(["solve"]);
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
      n_edited_runs: 1, n_finished_pictures: 1,
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
      n_edited_runs: 1, n_finished_pictures: 1,
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

describe("the step that is actually ahead of you", () => {
  // Photographed 2026-09-12 on the bundled sample, which is the app's own
  // first-run path (the Dashboard offers a "Stack it" button for it): the card
  // read "5 of 6 done" over five struck-through lines and led with **"Next:
  // Plate solving (ASTAP) is how AstroStack recognises the patch of sky in each
  // sub…"**. The ticks are not monotonic — `solve` measures *setup* while the
  // steps around it measure *outcomes* — so "the first unticked step" and "the
  // next thing to do" are different questions.

  const sampleFinished = () => firstImageSteps(sys({ found: false }), stats({
    n_frames: 6, n_frames_accepted: 6, n_stack_runs: 1,
    n_edited_runs: 1, n_finished_pictures: 1,
  }));

  it("never announces a step the user has already gone past", () => {
    const steps = sampleFinished();
    expect(steps.map((s) => s.done)).toEqual([true, false, true, true, true, true]);
    expect(firstImageNextStep(steps)).toBeNull();
    expect(firstImageLeadText(steps)).not.toMatch(/^Next:/);
  });

  it("still names the skipped step, and why it will matter", () => {
    // Nothing is hidden: ASTAP genuinely isn't set up and their own subs will
    // need it. It just stops being announced as what to do *next*.
    const steps = sampleFinished();
    expect(firstImageSkippedSteps(steps).map((s) => s.key)).toEqual(["solve"]);
    const lead = firstImageLeadText(steps);
    expect(lead).toMatch(/been all the way through/);
    expect(lead).toMatch(/your own subs/);
    expect(lead).toContain(steps[1].hint);
  });

  it("leads with the real next step whenever there is one ahead", () => {
    // The ordinary mid-journey case is untouched: nothing after `stack` is done,
    // so `stack` is both the first unticked step and the next thing to do.
    const steps = firstImageSteps(sys(), stats({ n_frames: 40, n_frames_accepted: 32 }));
    expect(firstImageNextStep(steps)?.key).toBe("stack");
    expect(firstImageSkippedSteps(steps)).toEqual([]);
    expect(firstImageLeadText(steps)).toBe(`Next: ${steps[3].hint}`);
  });

  it("keeps the plain description for a brand-new install", () => {
    // Nothing done at all: `frames` is ahead, so this is still a "Next:" line.
    const steps = firstImageSteps(sys({ found: false }), stats());
    expect(firstImageSkippedSteps(steps)).toEqual([]);
    expect(firstImageLeadText(steps)).toBe(`Next: ${steps[0].hint}`);
  });

  it("still sends a real first-timer with no ASTAP to the setup step", () => {
    // The guard on the fix. QC grades a sub with no plate solution at all, so
    // `checked` ticks for someone who cannot stack a thing — and a rule that
    // read "any later step is done" would call the setup overtaken and point
    // them at stacking, which is exactly what they can't do. Only `stack` and
    // beyond prove a solve happened, which is what `passedWhen` says.
    const steps = firstImageSteps(sys({ found: false }),
      stats({ n_frames: 40, n_frames_accepted: 32 }));
    expect(steps.map((s) => s.done)).toEqual([true, false, true, false, false, false]);
    expect(firstImageSkippedSteps(steps)).toEqual([]);
    expect(firstImageNextStep(steps)?.key).toBe("solve");
  });

  it("doesn't read an ASTAP install as progress through the journey", () => {
    // Setup done and nothing else: the one thing they have is the *second*
    // step, and the first is still genuinely ahead of them.
    const steps = firstImageSteps(sys(), stats());
    expect(steps.map((s) => s.done)).toEqual([false, true, false, false, false, false]);
    expect(firstImageNextStep(steps)?.key).toBe("frames");
    expect(firstImageSkippedSteps(steps)).toEqual([]);
  });

  it("only ever claims a step was passed by one that truly needs it", () => {
    // The table read back as a property: every key named in a `passedWhen` is a
    // real step, and it is always a *later* one — a step can only be proved by
    // something downstream of it.
    const steps = firstImageSteps(sys(), stats());
    const index = new Map(steps.map((s, i) => [s.key, i]));
    for (const [i, s] of steps.entries()) {
      for (const k of s.passedWhen ?? []) {
        expect(index.has(k)).toBe(true);
        expect(index.get(k)).toBeGreaterThan(i);
      }
    }
  });

  it("says it in the plural when more than one step was skipped", () => {
    // ASTAP missing *and* nothing edited, with a saved picture at the end — the
    // export-without-save shape, one step further along.
    const steps = firstImageSteps(sys({ found: false }), stats({
      n_frames: 6, n_frames_accepted: 0, n_stack_runs: 1, n_finished_pictures: 1,
    }));
    expect(firstImageSkippedSteps(steps).map((s) => s.key)).toEqual(["solve", "checked"]);
    expect(firstImageLeadText(steps)).toMatch(/aren't ticked/);
  });
});
