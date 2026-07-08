import { describe, expect, it } from "vitest";
import { folderReadiness } from "./folderReadiness";
import type { SystemInfo } from "../../api/client";

function folders(
  over: Partial<{
    incoming: { path: string; exists: boolean; writable: boolean };
    library: { path: string; exists: boolean; writable: boolean };
  }> = {},
): SystemInfo["folders"] {
  return {
    incoming: { path: "/data/incoming", exists: true, writable: true },
    library: { path: "/data/library", exists: true, writable: true },
    ...over,
  };
}

describe("folderReadiness", () => {
  it("is ready when both folders exist and are writable", () => {
    expect(folderReadiness(folders())).toEqual({ ready: true });
  });

  it("flags a missing incoming folder", () => {
    expect(folderReadiness(folders({ incoming: { path: "/x", exists: false, writable: false } })))
      .toEqual({ ready: false, kind: "incoming", problem: "missing" });
  });

  it("flags an unwritable incoming folder", () => {
    expect(folderReadiness(folders({ incoming: { path: "/x", exists: true, writable: false } })))
      .toEqual({ ready: false, kind: "incoming", problem: "unwritable" });
  });

  it("flags a missing library folder when incoming is fine", () => {
    expect(folderReadiness(folders({ library: { path: "/y", exists: false, writable: false } })))
      .toEqual({ ready: false, kind: "library", problem: "missing" });
  });

  it("flags an unwritable library folder when incoming is fine", () => {
    expect(folderReadiness(folders({ library: { path: "/y", exists: true, writable: false } })))
      .toEqual({ ready: false, kind: "library", problem: "unwritable" });
  });

  it("prefers the incoming problem over a library problem", () => {
    // Incoming is checked first — you can't even scan without it.
    expect(folderReadiness(folders({
      incoming: { path: "/x", exists: false, writable: false },
      library: { path: "/y", exists: false, writable: false },
    }))).toEqual({ ready: false, kind: "incoming", problem: "missing" });
  });

  it("does not nag when the backend omits the folders field (older backend)", () => {
    expect(folderReadiness(undefined)).toEqual({ ready: true });
  });
});
