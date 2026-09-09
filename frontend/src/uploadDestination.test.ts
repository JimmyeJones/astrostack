import { describe, expect, it } from "vitest";
import {
  destinationAdvice, normalizeTargetName, targetNameForFolder,
  type UploadDestination,
} from "./uploadDestination";

const M31: UploadDestination = { target: "M 31", folder: "M 31_sub", n_frames: 3110 };
const NGC: UploadDestination = { target: "NGC 6888", folder: "NGC 6888", n_frames: 42 };
const MOSAIC: UploadDestination = {
  target: "M 31 (mosaic)", folder: "M 31_mosaic_sub", n_frames: 900,
};

describe("targetNameForFolder", () => {
  it("mirrors the scanner's convention", () => {
    expect(targetNameForFolder("M 31_sub")).toBe("M 31");
    expect(targetNameForFolder("M 31_mosaic_sub")).toBe("M 31 (mosaic)");
    expect(targetNameForFolder("M 31")).toBe("M 31");
  });

  it("matches on the suffix case-insensitively, keeping the folder's own casing", () => {
    expect(targetNameForFolder("NGC 6888_SUB")).toBe("NGC 6888");
  });

  it("keeps a folder named only of the suffix — there is no base to fall back to", () => {
    expect(targetNameForFolder("_sub")).toBe("_sub");
    expect(targetNameForFolder("_mosaic_sub")).toBe("_mosaic_sub");
  });
});

describe("normalizeTargetName", () => {
  it("folds away only what a person does not mean", () => {
    expect(normalizeTargetName("M 31")).toBe(normalizeTargetName("M31"));
    expect(normalizeTargetName("M-31")).toBe(normalizeTargetName("m_31"));
    expect(normalizeTargetName("M 31")).not.toBe(normalizeTargetName("M 32"));
  });
});

describe("destinationAdvice", () => {
  it("says nothing about a blank box — the form already says 'Unsorted'", () => {
    expect(destinationAdvice("", [M31])).toBeNull();
    expect(destinationAdvice("   ", [M31])).toBeNull();
  });

  it("confirms an exact folder, naming the target and what is already there", () => {
    const a = destinationAdvice("M 31_sub", [M31, NGC])!;
    expect(a.tone).toBe("info");
    expect(a.message).toContain("M 31");
    expect(a.message).toContain("3,110");
    expect(a.fixFolder).toBeUndefined();
  });

  it("matches an existing folder case-insensitively, like the scanner does", () => {
    expect(destinationAdvice("m 31_SUB", [M31])!.tone).toBe("info");
  });

  it("warns about the bare folder beside a real _sub, and offers the fix", () => {
    // The trap: `M 31/` next to `M 31_sub/` is the Seestar's own finished
    // picture, which the scanner skips — so these subs would land and never
    // ingest. This is the one case where "the obvious name" loses the upload.
    const a = destinationAdvice("M 31", [M31])!;
    expect(a.tone).toBe("warn");
    expect(a.message).toContain("M 31_sub");
    expect(a.message).toContain("skip");
    expect(a.fixFolder).toBe("M 31_sub");
  });

  it("does NOT claim the skip for a mosaic sibling — the scanner only tests _sub", () => {
    // `_mosaic_sub` also ends in `_sub`, but the scanner's sibling test appends
    // exactly "_sub", so a bare `M 31/` next to `M 31_mosaic_sub/` is ingested,
    // not skipped. Saying otherwise would be a confident untruth.
    const a = destinationAdvice("M 31", [MOSAIC])!;
    expect(a.message).not.toContain("skip");
  });

  it("warns about a near-miss that would start a second target, and offers the fix", () => {
    const a = destinationAdvice("M31", [M31])!;
    expect(a.tone).toBe("warn");
    expect(a.message).toContain("second target");
    expect(a.message).toContain("M 31_sub");
    expect(a.fixFolder).toBe("M 31_sub");
  });

  it("recognises the near-miss through the folder→target convention", () => {
    // `M31_sub` is not `M 31_sub` and never matches a folder — but it *resolves*
    // to the target M 31, which already exists.
    const a = destinationAdvice("M31_sub", [M31])!;
    expect(a.tone).toBe("warn");
    expect(a.fixFolder).toBe("M 31_sub");
  });

  it("prefers the skip warning over the near-miss when both could fire", () => {
    // `M 31` matches the target name too, but the skip is the more specific and
    // more damaging outcome, so its wording wins.
    expect(destinationAdvice("M 31", [M31])!.message).toContain("skip");
  });

  it("warns about a capture folder the scanner never ingests", () => {
    const a = destinationAdvice("M 31_video", [M31])!;
    expect(a.tone).toBe("warn");
    expect(a.message).toContain("_video");
    expect(a.fixFolder).toBeUndefined();
    expect(destinationAdvice("Scenery_photo", [])!.tone).toBe("warn");
  });

  it("warns about another program's scratch folder, by exact name", () => {
    expect(destinationAdvice("batch_stack_tmp", [])!.tone).toBe("warn");
    expect(destinationAdvice("batch_stack_tmp2", [])!.tone).toBe("info");
  });

  it("says what a brand-new name will become, including the _sub rename", () => {
    const plain = destinationAdvice("M 106", [M31])!;
    expect(plain.tone).toBe("info");
    expect(plain.message).toContain("M 106");

    const sub = destinationAdvice("M 106_sub", [M31])!;
    expect(sub.tone).toBe("info");
    expect(sub.message).toContain("M 106");
    expect(sub.message).toContain("M 106_sub");
  });

  it("degrades to the plain new-target line when the destinations are unknown", () => {
    // An older backend (or a failed read) yields none: the box must behave
    // exactly as it did, never warn on no evidence.
    const a = destinationAdvice("M 31", [])!;
    expect(a.tone).toBe("info");
    expect(a.fixFolder).toBeUndefined();
  });
});
