import { describe, expect, it } from "vitest";
import { formatIntegration } from "./format";

describe("formatIntegration", () => {
  it("formats each unit range", () => {
    expect(formatIntegration(8)).toBe("8 s");
    expect(formatIntegration(150)).toBe("3 min");
    expect(formatIntegration(8280)).toBe("2.3 h");
    expect(formatIntegration(36000)).toBe("10 h");
  });

  it("returns an em dash for zero / non-finite input", () => {
    expect(formatIntegration(0)).toBe("—");
    expect(formatIntegration(-5)).toBe("—");
    expect(formatIntegration(NaN)).toBe("—");
  });

  it("promotes a value that rounds up to a whole unit instead of printing '60 min' / '60 s'", () => {
    // 3599 s is 59.98 min — must read as ~1 h, not "60 min".
    expect(formatIntegration(3599)).toBe("1.0 h");
    // 59.9 s rounds to a whole minute, not "60 s".
    expect(formatIntegration(59.9)).toBe("1 min");
    // A genuine sub-boundary value stays in its own unit.
    expect(formatIntegration(30)).toBe("30 s");
    expect(formatIntegration(3000)).toBe("50 min");
  });
});
