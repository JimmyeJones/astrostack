import { describe, expect, it } from "vitest";
import type { Job } from "../api/client";
import { activeStackJobFor, processStartedMessage } from "./useTargetStackJob";

function job(over: Partial<Job>): Job {
  return {
    id: "j", kind: "process_target", target: "M_42", state: "queued", phase: "",
    done: 0, total: 0, detail: "", created_utc: null, started_utc: null,
    finished_utc: null, error: null, ...over,
  } as Job;
}

describe("activeStackJobFor", () => {
  it("finds a queued or running process/stack job of this target", () => {
    expect(activeStackJobFor([job({ id: "a" })], "M_42")?.id).toBe("a");
    expect(activeStackJobFor([job({ id: "b", state: "running", kind: "stack" })], "M_42")?.id)
      .toBe("b");
  });

  it("ignores finished jobs, other targets and other kinds", () => {
    expect(activeStackJobFor([
      job({ state: "done" }), job({ state: "error" }), job({ state: "cancelled" }),
      job({ target: "M_31" }), job({ kind: "qc_solve" }), job({ target: null }),
    ], "M_42")).toBeNull();
  });

  it("is null with no job list (loading, older backend, failed fetch)", () => {
    expect(activeStackJobFor(undefined, "M_42")).toBeNull();
    expect(activeStackJobFor(null, "M_42")).toBeNull();
  });
});

describe("processStartedMessage", () => {
  it("says nothing new was queued when the server handed back the waiting job", () => {
    expect(processStartedMessage(true, "fresh")).toMatch(/already waiting its turn/);
    expect(processStartedMessage(true, "fresh")).toMatch(/nothing new was queued/);
  });

  it("keeps the caller's message for a fresh job or an older backend", () => {
    expect(processStartedMessage(false, "fresh")).toBe("fresh");
    expect(processStartedMessage(undefined, "fresh")).toBe("fresh");
  });
});
