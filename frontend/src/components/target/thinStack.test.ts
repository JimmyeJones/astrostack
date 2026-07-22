import { describe, it, expect } from "vitest";

import { thinStackWarning, THIN_STACK_MAX_FRAMES } from "./thinStack";

describe("thinStackWarning", () => {
  it("returns null for a healthy frame count", () => {
    expect(thinStackWarning(5)).toBeNull();
    expect(thinStackWarning(50)).toBeNull();
    expect(thinStackWarning(THIN_STACK_MAX_FRAMES + 1)).toBeNull();
  });

  it("returns null when the count is unknown or invalid", () => {
    expect(thinStackWarning(null)).toBeNull();
    expect(thinStackWarning(undefined)).toBeNull();
    expect(thinStackWarning(NaN)).toBeNull();
    expect(thinStackWarning(-3)).toBeNull();
  });

  it("flags a single-frame 'stack' as not really a stack", () => {
    const w = thinStackWarning(1);
    expect(w?.level).toBe("single");
    expect(w?.frames).toBe(1);
    expect(w?.message).toMatch(/single sub/);
    expect(w?.message).toMatch(/plate-solved/);
  });

  it("treats a zero-frame stack as the single (most severe) level", () => {
    expect(thinStackWarning(0)?.level).toBe("single");
  });

  it("flags a very thin (2–4 frame) stack as noisy but distinct from single", () => {
    for (const n of [2, 3, 4]) {
      const w = thinStackWarning(n);
      expect(w?.level).toBe("thin");
      expect(w?.frames).toBe(n);
      expect(w?.message).toMatch(new RegExp(`only ${n} frames`));
    }
  });
});
