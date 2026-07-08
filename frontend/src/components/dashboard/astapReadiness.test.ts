import { describe, expect, it } from "vitest";
import { astapReadiness, astapReadinessSignature } from "./astapReadiness";
import type { SystemInfo } from "../../api/client";

function astap(over: Partial<SystemInfo["astap"]> = {}): SystemInfo["astap"] {
  return { found: true, path: "/usr/bin/astap", star_db_found: true, ...over };
}

describe("astapReadiness", () => {
  it("is ready when ASTAP and a star database are both present", () => {
    expect(astapReadiness(astap())).toEqual({ ready: true });
  });

  it("flags ASTAP missing before the database", () => {
    // ASTAP missing takes precedence — without the solver a database is moot.
    expect(astapReadiness(astap({ found: false, star_db_found: false })))
      .toEqual({ ready: false, kind: "astap" });
  });

  it("flags a missing star database when ASTAP is found", () => {
    expect(astapReadiness(astap({ found: true, star_db_found: false })))
      .toEqual({ ready: false, kind: "database" });
  });

  it("does not nag when the backend omits star_db_found (older backend)", () => {
    // Only a *definite* false counts, so an old backend without the field never
    // shows a spurious "database missing".
    expect(astapReadiness(astap({ found: true, star_db_found: undefined })))
      .toEqual({ ready: true });
  });

  it("does not nag when system info hasn't loaded yet", () => {
    expect(astapReadiness(undefined)).toEqual({ ready: true });
  });
});

describe("astapReadinessSignature", () => {
  it("is null when ready (nothing to dismiss)", () => {
    expect(astapReadinessSignature({ ready: true })).toBeNull();
  });

  it("distinguishes the astap and database problems", () => {
    // A different signature is what lets a later/different problem re-surface
    // after an earlier one was dismissed.
    expect(astapReadinessSignature({ ready: false, kind: "astap" })).toBe("astap");
    expect(astapReadinessSignature({ ready: false, kind: "database" })).toBe("database");
  });
});
