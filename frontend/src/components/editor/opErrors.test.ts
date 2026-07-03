import { describe, it, expect } from "vitest";
import { opErrorsMessage } from "./opErrors";

describe("opErrorsMessage", () => {
  it("returns null for no failures", () => {
    expect(opErrorsMessage([])).toBeNull();
    expect(opErrorsMessage(undefined)).toBeNull();
    expect(opErrorsMessage(null)).toBeNull();
    expect(opErrorsMessage("not an array")).toBeNull();
  });

  it("names a single failed op (singular)", () => {
    const msg = opErrorsMessage(["Saturation: RuntimeError: kaboom"]);
    expect(msg).toContain("1 operation failed");
    expect(msg).toContain("Saturation: RuntimeError: kaboom");
  });

  it("joins multiple failures (plural)", () => {
    const msg = opErrorsMessage(["Saturation: err a", "Sharpen: err b"]);
    expect(msg).toContain("2 operations failed");
    expect(msg).toContain("Saturation: err a");
    expect(msg).toContain("Sharpen: err b");
  });

  it("ignores blank / non-string entries", () => {
    const msg = opErrorsMessage(["", "  ", 42, null, "Curves: boom"]);
    expect(msg).toContain("1 operation failed");
    expect(msg).toContain("Curves: boom");
  });
});
