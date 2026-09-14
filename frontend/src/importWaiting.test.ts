import { describe, expect, it } from "vitest";
import type { ImportWaiting } from "./api/client";
import { importWaitingNote, waitedFor } from "./importWaiting";

const label = (kind: string) =>
  ({ reprocess_all: "Reprocessing all targets", stack: "Stacking" })[kind] ?? kind;

function waiting(o: Partial<ImportWaiting> = {}): ImportWaiting {
  return {
    job_id: "imp", queued_utc: "2026-09-11T01:04:48Z", waiting_hours: 70,
    n_waiting: 1, holder_id: "rep", holder_kind: "reprocess_all",
    holder_target: null, holder_hours: 96, ...o,
  };
}

describe("waitedFor", () => {
  it("reads in hours below a day and days beyond it", () => {
    expect(waitedFor(2.4)).toBe("2.4 hours");
    expect(waitedFor(1)).toBe("1 hour");
    expect(waitedFor(13.2)).toBe("13 hours");
    // 70.4 h is a number a reader has to divide; the whole point is that it lands.
    expect(waitedFor(70.4)).toBe("3 days");
    expect(waitedFor(24)).toBe("1 day");
  });

  it("says nothing for a missing, zero or nonsense duration", () => {
    expect(waitedFor(null)).toBe("");
    expect(waitedFor(undefined)).toBe("");
    expect(waitedFor(0)).toBe("");
    expect(waitedFor(-3)).toBe("");
    expect(waitedFor(Number.NaN)).toBe("");
  });
});

describe("importWaitingNote", () => {
  it("says nothing on a healthy queue", () => {
    expect(importWaitingNote(null, label)).toBeNull();
    expect(importWaitingNote(undefined, label)).toBeNull();
  });

  it("names the holder in plain language and what to do about it", () => {
    const note = importWaitingNote(waiting(), label);
    expect(note).not.toBeNull();
    expect(note!.title).toBe("New frames are waiting to be imported");
    expect(note!.body).toContain("waiting 3 days");
    // The engine's own kind must never reach the screen.
    expect(note!.body).toContain("“Reprocessing all targets”");
    expect(note!.body).not.toContain("reprocess_all");
    expect(note!.body).toContain("running for 4 days");
    expect(note!.body).toContain("cancel it on the Jobs page");
  });

  it("always says the subs themselves are safe", () => {
    // The first thing a beginner reading "your frames aren't imported" needs.
    const note = importWaitingNote(waiting(), label);
    expect(note!.reassurance).toContain("Nothing is lost");
    expect(note!.reassurance).toContain("incoming folder");
  });

  it("names the target when the holder has one", () => {
    const note = importWaitingNote(
      waiting({ holder_kind: "stack", holder_target: "NGC 6888" }), label);
    expect(note!.body).toContain("“Stacking” on NGC 6888");
  });

  it("does not invent a duration for a holder that never recorded a start", () => {
    const note = importWaitingNote(waiting({ holder_hours: null }), label);
    expect(note!.body).toContain("“Reprocessing all targets”.");
    expect(note!.body).not.toContain("running for");
  });

  it("tells a different story when nothing is running at all", () => {
    // Not busy — stalled. "Wait for it to finish" would be advice about a job
    // that does not exist.
    const note = importWaitingNote(
      waiting({ holder_id: null, holder_kind: null, holder_hours: null }), label);
    expect(note!.body).toContain("nothing is running");
    expect(note!.body).toContain("Restarting AstroStack");
    expect(note!.body).not.toContain("cancel it");
  });

  it("counts the imports when more than one has piled up", () => {
    const note = importWaitingNote(waiting({ n_waiting: 3 }), label);
    expect(note!.title).toBe("3 imports are waiting to run");
  });

  it("declines rather than printing an empty duration", () => {
    expect(importWaitingNote(waiting({ waiting_hours: 0 }), label)).toBeNull();
    expect(importWaitingNote(waiting({ waiting_hours: Number.NaN }), label)).toBeNull();
  });
});
