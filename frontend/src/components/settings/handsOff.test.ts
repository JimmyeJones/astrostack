import { describe, expect, it } from "vitest";
import {
  HANDS_OFF_PRESETS, handsOffPatch, handsOffPreset, PIPELINE_FIELDS, PIPELINE_STEPS,
  pipelineUnsaved, quietWords, stepState,
} from "./handsOff";

const ALL_ON = Object.fromEntries(PIPELINE_FIELDS.map((f) => [f, true]));

describe("hands-off cards", () => {
  it("map onto the six pipeline fields exactly as the approved spec says", () => {
    expect(handsOffPatch("all")).toEqual({
      watcher_enabled: true, auto_ingest: true, auto_qc: true, auto_solve: true,
      auto_stack: true, auto_edit_on_autostack: true,
    });
    expect(handsOffPatch("ready")).toEqual({
      watcher_enabled: true, auto_ingest: true, auto_qc: true, auto_solve: true,
      auto_stack: false, auto_edit_on_autostack: false,
    });
    expect(handsOffPatch("manual")).toEqual(
      Object.fromEntries(PIPELINE_FIELDS.map((f) => [f, false])));
  });

  it("recognise the owner's own setup — everything on but stacking — as \"Get them ready\"", () => {
    expect(handsOffPreset({ ...ALL_ON, auto_stack: false, auto_edit_on_autostack: false }))
      .toBe("ready");
    // A fresh install ships all six on.
    expect(handsOffPreset(ALL_ON)).toBe("all");
    expect(handsOffPreset({})).toBe("manual");
  });

  it("pick no card for a hand-made mix, and change nothing for it", () => {
    expect(handsOffPreset({ ...ALL_ON, auto_qc: false })).toBeNull();
    expect(handsOffPreset({ ...ALL_ON, auto_stack: false })).toBeNull();
  });

  it("each card round-trips: picking it reads back as it", () => {
    for (const p of HANDS_OFF_PRESETS) {
      expect(handsOffPreset(handsOffPatch(p.id))).toBe(p.id);
    }
  });

  it("only write the six pipeline fields", () => {
    for (const p of HANDS_OFF_PRESETS) {
      expect(Object.keys(handsOffPatch(p.id)).sort()).toEqual([...PIPELINE_FIELDS].sort());
    }
  });

  it("say a picked card is not saved until it is", () => {
    const saved = { ...ALL_ON, auto_stack: false, auto_edit_on_autostack: false };
    expect(pipelineUnsaved(saved, saved)).toBe(false);
    expect(pipelineUnsaved({ ...saved, ...handsOffPatch("all") }, saved)).toBe(true);
    // An unrelated edit is not this section's to report.
    expect(pipelineUnsaved({ ...saved, copy_to_cache: true }, saved)).toBe(false);
  });
});

describe("the six-step row — what really waits for what", () => {
  it("runs every step on its own when all six are on", () => {
    for (const f of PIPELINE_FIELDS) expect(stepState(ALL_ON, f)).toBe("auto");
  });

  it("holds every later step when Notice is off — nothing starts a scan by itself", () => {
    const form = { ...ALL_ON, watcher_enabled: false };
    expect(stepState(form, "watcher_enabled")).toBe("manual");
    for (const f of PIPELINE_FIELDS.slice(1)) expect(stepState(form, f)).toBe("waiting");
  });

  it("does NOT hold Place, Stack or Finish when only Check is off", () => {
    // The spec's "everything after it waits" is not what the pipeline does:
    // `_pipeline_body` solves with run_qc=False, and auto-stack is its own pass.
    // Drawing these as waiting would tell the owner his stacks had stopped.
    const form = { ...ALL_ON, auto_qc: false };
    expect(stepState(form, "auto_qc")).toBe("manual");
    expect(stepState(form, "auto_solve")).toBe("auto");
    expect(stepState(form, "auto_stack")).toBe("auto");
    expect(stepState(form, "auto_edit_on_autostack")).toBe("auto");
  });

  it("holds Stack and Finish when Place is off — auto-stack only takes placed subs", () => {
    const form = { ...ALL_ON, auto_solve: false };
    expect(stepState(form, "auto_qc")).toBe("auto");
    expect(stepState(form, "auto_stack")).toBe("waiting");
    expect(stepState(form, "auto_edit_on_autostack")).toBe("waiting");
  });

  it("holds Finish when Stack is off, and calls a switched-off Finish yours", () => {
    expect(stepState({ ...ALL_ON, auto_stack: false }, "auto_edit_on_autostack")).toBe("waiting");
    expect(stepState({ ...ALL_ON, auto_edit_on_autostack: false }, "auto_edit_on_autostack"))
      .toBe("manual");
  });

  it("names each step's prerequisite as an earlier step", () => {
    PIPELINE_STEPS.forEach((s, i) => {
      if (s.needs === null) return;
      expect(PIPELINE_FIELDS.indexOf(s.needs)).toBeLessThan(i);
    });
  });

  it("keeps the old labels for the Was: line", () => {
    expect(PIPELINE_STEPS.map((s) => s.was)).toEqual([
      "Watch for new files automatically", "Ingest", "QC", "Plate-solve", "Auto-stack",
      "Auto-edit the auto-stacked master into a finished picture",
    ]);
  });

  it("says the Notice step's real wait, from watch_quiet_period_s", () => {
    expect(quietWords(30)).toBe("30\u00a0s");
    expect(quietWords(90)).toBe("1.5\u00a0min");
    expect(quietWords(undefined)).toBe("30\u00a0s");
    expect(PIPELINE_STEPS[0].desc(quietWords(45))).toMatch(/waits 45\s+s after copying stops/);
  });
});
