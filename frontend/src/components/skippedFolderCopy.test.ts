import { describe, expect, it } from "vitest";
import {
  skipReasonOf, skippedFolderLine, skippedFoldersCardTitle,
  skippedFoldersExplainer, skippedFoldersTitle,
} from "./skippedFolderCopy";

describe("skipReasonOf", () => {
  it("reads an older backend's silence as the only case it could produce", () => {
    // Upgrade-safety: the field is additive, so a backend that predates it sends
    // nothing — which must not read as a temp folder, and must not be dropped.
    expect(skipReasonOf(undefined)).toBe("device_output");
    expect(skipReasonOf(null)).toBe("device_output");
    expect(skipReasonOf("something_new")).toBe("device_output");
    expect(skipReasonOf(7)).toBe("device_output");
    expect(skipReasonOf("temp_folder")).toBe("temp_folder");
  });
});

describe("the two titles", () => {
  it("keeps each surface's own question rather than one shared sentence", () => {
    // The Jobs alert reports what a scan did; the Library card answers "are some
    // of my subs missing from my pictures?". Collapsing them would make one of
    // the two wrong, so they are deliberately different sentences.
    expect(skippedFoldersTitle(["device_output"]))
      .toBe("Some folders were skipped as your Seestar's own pictures");
    expect(skippedFoldersCardTitle(["device_output"]))
      .toBe("Some of your subs may not be reaching a picture");
  });

  it("stops claiming a scratch directory is your Seestar's own picture", () => {
    expect(skippedFoldersTitle(["temp_folder"]))
      .toBe("Another program's working folder was skipped");
    // …and the card drops the "your subs" framing, because none of the owner's
    // subs are missing when the skipped folder belongs to another program.
    expect(skippedFoldersCardTitle(["temp_folder"]))
      .toBe("A folder in your incoming folder was skipped");
    expect(skippedFoldersCardTitle(["temp_folder", "temp_folder"]))
      .toBe("Some folders in your incoming folder were skipped");
  });

  it("lets the missing-subs question win when both reasons are present", () => {
    // A real folder of the owner's subs is the more consequential finding, so
    // the card leads with it; the Jobs alert names neither rule over the other.
    expect(skippedFoldersCardTitle(["temp_folder", "device_output"]))
      .toBe("Some of your subs may not be reaching a picture");
    expect(skippedFoldersTitle(["temp_folder", "device_output"]))
      .toBe("Some folders in your incoming folder were skipped");
  });
});

describe("skippedFoldersExplainer", () => {
  it("says only what applies, and always says nothing was touched", () => {
    const device = skippedFoldersExplainer(["device_output"]);
    expect(device).toContain("finished picture your Seestar made");
    expect(device).not.toContain("another stacking program");

    const temp = skippedFoldersExplainer(["temp_folder"]);
    expect(temp).toContain("another stacking program leaves behind");
    expect(temp).not.toContain("finished picture your Seestar made");

    for (const text of [device, temp, skippedFoldersExplainer([])]) {
      expect(text).toContain("nothing was deleted, moved or renamed");
    }
  });

  it("reads as one explanation when a scan hits both rules", () => {
    const both = skippedFoldersExplainer(["temp_folder", "device_output"]);
    // Fixed order regardless of the order the folders arrived in, so the same
    // scan never reads two different ways.
    expect(both.indexOf("finished picture your Seestar made"))
      .toBeLessThan(both.indexOf("another stacking program leaves behind"));
  });
});

describe("skippedFolderLine", () => {
  it("names what was skipped and why, per folder", () => {
    expect(skippedFolderLine({
      name: "NGC 6888", nFiles: 4815, nUnrecognised: 4815,
      reason: "device_output",
    })).toBe("NGC 6888: 4,815 files skipped, 4,815 of them not recognised as "
      + "your Seestar's own picture.");
    expect(skippedFolderLine({
      name: "batch_stack_tmp", nFiles: 137, nUnrecognised: 0,
      reason: "temp_folder",
    })).toBe("batch_stack_tmp: 137 files skipped — another stacking program's "
      + "working folder.");
  });

  it("pluralises the file count", () => {
    expect(skippedFolderLine({
      name: "M 13", nFiles: 1, nUnrecognised: 1, reason: "temp_folder",
    })).toContain("1 file skipped");
  });
});
