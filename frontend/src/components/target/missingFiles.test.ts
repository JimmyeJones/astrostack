import { describe, it, expect } from "vitest";
import { missingFilesNote } from "./missingFiles";

describe("missingFilesNote", () => {
  it("says nothing when every accepted sub is readable", () => {
    expect(missingFilesNote(0, 500)).toBeNull();
  });

  it("says nothing when an older backend omits the counts", () => {
    expect(missingFilesNote(undefined, undefined)).toBeNull();
    expect(missingFilesNote(12, undefined)).toBeNull();
    expect(missingFilesNote(undefined, 500)).toBeNull();
  });

  it("says nothing for a target with no accepted subs", () => {
    expect(missingFilesNote(3, 0)).toBeNull();
  });

  it("ignores garbled counts rather than rendering NaN", () => {
    expect(missingFilesNote(Number.NaN, 500)).toBeNull();
    expect(missingFilesNote(12, Number.NaN)).toBeNull();
    expect(missingFilesNote(-4, 500)).toBeNull();
  });

  it("names how many are gone, out of how many, and the fix", () => {
    const note = missingFilesNote(142, 500);
    expect(note).not.toBeNull();
    expect(note!.missing).toBe(142);
    expect(note!.total).toBe(500);
    expect(note!.title).toBe("142 of 500 subs aren't on disk");
    expect(note!.message).toContain("142 of this target's 500 accepted subs");
    expect(note!.message).toContain("their files aren't on disk right now");
    expect(note!.message).toContain("check it's connected");
  });

  it("reads naturally for a single missing sub", () => {
    const note = missingFilesNote(1, 20);
    expect(note!.title).toBe("1 of 20 subs aren't on disk");
    expect(note!.message).toContain("its file isn't on disk");
    expect(note!.message).toContain("it can't be stacked");
  });

  it("says so plainly when the whole target has vanished", () => {
    const note = missingFilesNote(500, 500);
    expect(note!.title).toBe("This target's 500 subs aren't on disk");
    expect(note!.message).toContain("Every one of this target's 500 accepted subs");
  });

  it("clamps a count that exceeds the population it was taken over", () => {
    const note = missingFilesNote(600, 500);
    expect(note!.missing).toBe(500);
    expect(note!.title).toBe("This target's 500 subs aren't on disk");
  });
});
