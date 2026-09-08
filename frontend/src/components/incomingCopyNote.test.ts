import { describe, expect, it } from "vitest";
import { incomingCopyNote } from "./incomingCopyNote";

const fmt = (b: number) => `${(b / 1024 ** 3).toFixed(0)} GB`;

describe("incomingCopyNote", () => {
  it("says how many subs are in incoming/, how big they are, and who backs them up", () => {
    const note = incomingCopyNote(
      { incoming_frames: 8542, incoming_bytes: 44 * 1024 ** 3, incoming_copied: false },
      fmt,
    );
    expect(note).toContain("8,542 subs");
    expect(note).toContain("(44 GB)");
    expect(note).toContain("only copy");
    expect(note).toContain("nothing this app does backs them up");
    expect(note).toContain("Keep a copy somewhere else");
    // Not "at least" when every frame's size is known.
    expect(note).not.toContain("at least");
  });

  it("says 'at least' when some frames predate the size column", () => {
    const note = incomingCopyNote(
      { incoming_frames: 100, incoming_bytes: 2 * 1024 ** 3, incoming_unsized_frames: 7 },
      fmt,
    );
    expect(note).toContain("(at least 2 GB)");
    expect(note).toContain("100 subs");
  });

  it("drops the size entirely when no frame has one", () => {
    const note = incomingCopyNote({ incoming_frames: 12, incoming_bytes: 0 }, fmt);
    expect(note).toContain("12 subs in incoming/");
    expect(note).not.toContain("(");
  });

  it("says what the cache copies are when copy_to_cache is on", () => {
    const note = incomingCopyNote(
      { incoming_frames: 5, incoming_bytes: 1024 ** 3, incoming_copied: true },
      fmt,
    );
    // Still not a backup — but the app *is* holding something, and says what.
    expect(note).toContain("Clear caches deletes");
    expect(note).toContain("not a backup");
    expect(note).not.toContain("keeps no copy of its own");
  });

  it("says nothing on a fresh install or against an older backend", () => {
    expect(incomingCopyNote({ incoming_frames: 0 }, fmt)).toBeNull();
    expect(incomingCopyNote({}, fmt)).toBeNull();
  });

  it("uses the singular for one sub", () => {
    const note = incomingCopyNote({ incoming_frames: 1, incoming_bytes: 0 }, fmt);
    expect(note).toContain("1 sub in incoming/");
  });
});
