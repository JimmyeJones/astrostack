import { describe, expect, it } from "vitest";
import type { ImportWaiting } from "./api/client";
import {
  importIsWaiting, importWaitingNote, incomingLagCause, incomingLagUnreadable,
  waitedFor,
} from "./importWaiting";

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

describe("importIsWaiting", () => {
  it("is exactly the condition importWaitingNote speaks on", () => {
    // The whole point of the predicate: one note may only defer to another if
    // the two ask the identical question. Checked at the boundary, not just in
    // the middle — `waitedFor` is what decides both.
    for (const hours of [70, 24, 1, 0.5, 0, -3, Number.NaN]) {
      const w = waiting({ waiting_hours: hours });
      expect(importIsWaiting(w)).toBe(importWaitingNote(w, label) !== null);
    }
  });

  it("answers false for a backend that has no such endpoint", () => {
    expect(importIsWaiting(null)).toBe(false);
    expect(importIsWaiting(undefined)).toBe(false);
  });
});

describe("incomingLagCause", () => {
  it("quotes the queue rather than guessing, and withholds the scan", () => {
    const c = incomingLagCause(waiting({ waiting_hours: 264 }));
    expect(c.sentence).toContain("already queued and has been waiting 11 days");
    expect(c.sentence).not.toContain("usually means");
    // A serial worker: a second scan joins the back of the queue the first one
    // is already at the front of.
    expect(c.scanHelps).toBe(false);
    expect(c.sentence).toContain("only add a second job behind it");
  });

  it("drops the reassurance the stuck-import note is already giving", () => {
    // Both notes rank `warning` and the board keeps two inline, so repeating
    // "nothing is lost" would spend half of what the owner reads on one
    // sentence said twice.
    expect(incomingLagCause(waiting()).reassurance).toBe("");
    expect(incomingLagCause(null).reassurance).toContain("Nothing is lost");
  });

  it("says a scan is the answer when the queue really is empty", () => {
    for (const w of [null, undefined, waiting({ waiting_hours: 0 })]) {
      const c = incomingLagCause(w);
      expect(c.scanHelps).toBe(true);
      expect(c.sentence).toContain("nothing is queued waiting to run");
      // And never claims a wait it cannot see.
      expect(c.sentence).not.toContain("already queued");
    }
  });
});

describe("incomingLagUnreadable", () => {
  it("says nothing at all when nothing is damaged", () => {
    expect(incomingLagUnreadable(2259, 0)).toBeNull();
    // An older backend sends no count, and a negative or junk one is not a
    // finding either — all three read as the previous behaviour exactly.
    expect(incomingLagUnreadable(2259, undefined)).toBeNull();
    expect(incomingLagUnreadable(2259, null)).toBeNull();
    expect(incomingLagUnreadable(2259, -4)).toBeNull();
  });

  it("drops the delay framing when every waiting file is damaged", () => {
    const got = incomingLagUnreadable(6, 6);
    expect(got).not.toBeNull();
    expect(got!.all).toBe(true);
    expect(got!.title).toBe("6 subs in your incoming folder can't be read");
    expect(got!.sentence).toContain("a scan won't help");
    expect(got!.sentence).toContain("copying them over again");
    // The reassurance the cause sentence would have carried, which stands aside
    // on this branch — so it is said here exactly once.
    expect(got!.sentence).toContain("never changes anything in that folder");
  });

  it("keeps the delay headline when only some are damaged", () => {
    const got = incomingLagUnreadable(2259, 3);
    expect(got!.all).toBe(false);
    // Null title = the caller's own headline stands, because most of these
    // really are waiting.
    expect(got!.title).toBeNull();
    expect(got!.sentence).toMatch(/^3 of these can't be read at all/);
    // The board has room for two notes; the reassurance directly above this one
    // already says AstroStack never writes to that folder, so this must not.
    expect(got!.sentence).not.toContain("never changes anything in that folder");
  });

  it("uses singular wording for one damaged file", () => {
    const got = incomingLagUnreadable(1, 1);
    expect(got!.title).toBe("A sub in your incoming folder can't be read");
    expect(got!.sentence).toContain("copying it over again");
  });

  it("can never claim more damaged files than are waiting", () => {
    // The record and the listing are two snapshots taken at different moments,
    // so a folder whose damaged files have since been deleted must not report
    // more unreadable than waiting — and must still read as "all".
    const got = incomingLagUnreadable(2, 9);
    expect(got!.all).toBe(true);
    expect(got!.title).toBe("2 subs in your incoming folder can't be read");
  });
});
