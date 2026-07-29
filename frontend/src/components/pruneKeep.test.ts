import { describe, expect, it } from "vitest";
import { sanitizeKeep } from "./pruneKeep";

describe("sanitizeKeep", () => {
  it("rejects the emptied-box footgun so prune never means 'delete everything'", () => {
    // Number("") === 0, which the backend would honour as keep-nothing.
    expect(sanitizeKeep("", 10)).toBeNull();
    expect(sanitizeKeep("   ", 10)).toBeNull();
    expect(sanitizeKeep(0, 10)).toBeNull();
    expect(sanitizeKeep(-3, 10)).toBeNull();
  });

  it("rejects non-integer / non-numeric input", () => {
    expect(sanitizeKeep("abc", 10)).toBeNull();
    expect(sanitizeKeep(2.5, 10)).toBeNull();
  });

  it("passes a valid positive keep-count through", () => {
    expect(sanitizeKeep(3, 10)).toBe(3);
    expect(sanitizeKeep("5", 10)).toBe(5);   // NumberInput may hand back a string
  });

  it("clamps a keep-count larger than the run count (harmless, deletes nothing)", () => {
    expect(sanitizeKeep(50, 8)).toBe(8);
    expect(sanitizeKeep(1, 0)).toBe(1);      // no runs known → leave the value as typed
  });
});
