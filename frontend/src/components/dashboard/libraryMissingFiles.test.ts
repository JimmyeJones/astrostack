import { describe, expect, it } from "vitest";
import { libraryMissingFilesNote } from "./libraryMissingFiles";

describe("libraryMissingFilesNote", () => {
  it("says it once for the whole library, naming the cause and the fix", () => {
    const note = libraryMissingFilesNote({
      n_missing: 3200,
      n_accepted: 8000,
      n_targets_missing: 11,
      targets: Array.from({ length: 5 }, (_, i) => ({
        safe: `t${i}`, name: `Target ${i}`, n_missing: 291,
      })),
    });
    expect(note?.title).toBe("3,200 subs across 11 targets aren't on disk");
    expect(note?.message).toContain("drive or network share is offline");
    expect(note?.message).toContain("scan again");
    // Nowhere to point when eleven targets are affected.
    expect(note?.onlyTargetSafe).toBeNull();
  });

  it("names the one target when only one is affected, and links to it", () => {
    const note = libraryMissingFilesNote({
      n_missing: 412,
      n_accepted: 900,
      n_targets_missing: 1,
      targets: [{ safe: "orion", name: "Orion Nebula", n_missing: 412 }],
    });
    expect(note?.title).toBe("412 of Orion Nebula's subs aren't on disk");
    expect(note?.onlyTargetSafe).toBe("orion");
    expect(note?.targets).toBe(1);
  });

  it("reads naturally for a single sub", () => {
    const note = libraryMissingFilesNote({
      n_missing: 1, n_accepted: 50, n_targets_missing: 1,
      targets: [{ safe: "m31", name: "", n_missing: 1 }],
    });
    expect(note?.title).toBe("1 sub isn't on disk");
    expect(note?.message).toContain("its file isn't on disk");
    expect(note?.message).not.toContain("their files");
  });

  it("stays silent when nothing is missing, or when the answer isn't there", () => {
    expect(libraryMissingFilesNote({
      n_missing: 0, n_accepted: 8000, n_targets_missing: 0, targets: [],
    })).toBeNull();
    expect(libraryMissingFilesNote(null)).toBeNull();
    expect(libraryMissingFilesNote(undefined)).toBeNull();
    expect(libraryMissingFilesNote({
      n_missing: Number.NaN, n_accepted: 10, n_targets_missing: 0, targets: [],
    })).toBeNull();
  });

  it("still speaks when the count arrives without the affected list", () => {
    const note = libraryMissingFilesNote({
      n_missing: 7, n_accepted: 90, n_targets_missing: 0, targets: [],
    });
    expect(note?.title).toBe("7 subs aren't on disk");
    expect(note?.onlyTargetSafe).toBeNull();
  });

  it("counts the targets from the total, not from the capped list", () => {
    // A library-wide outage affects every target; the payload lists only the
    // worst few, so reading the count off the list would badly understate it.
    const note = libraryMissingFilesNote({
      n_missing: 9000,
      n_accepted: 9000,
      n_targets_missing: 40,
      targets: [{ safe: "a", name: "A", n_missing: 500 }],
    });
    expect(note?.title).toBe("9,000 subs across 40 targets aren't on disk");
    expect(note?.onlyTargetSafe).toBeNull();
  });
});
