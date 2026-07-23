import { describe, it, expect } from "vitest";
import { storageHeadroom } from "./storageHeadroom";

const GB = 1024 ** 3;

describe("storageHeadroom", () => {
  it("projects plenty of nights as healthy", () => {
    const h = storageHeadroom({
      freeBytes: 100 * GB,
      nightlyBytes: 1 * GB, // ~1 GB/night
      reclaimableCacheBytes: 5 * GB,
    });
    expect(h.level).toBe("healthy");
    expect(h.nightsLeft).toBe(100);
    expect(h.sentence).toContain("100 more nights");
    expect(h.sentence).toContain("GB free");
    expect(h.sentence).toContain("GB/night");
    expect(h.reclaimHint).toBeNull(); // no nudge when there's plenty of room
  });

  it("warns and offers a reclaim hint when space is short", () => {
    const h = storageHeadroom({
      freeBytes: 3 * GB,
      nightlyBytes: 1 * GB, // 3 nights left → short (< 5)
      reclaimableCacheBytes: 8 * GB,
    });
    expect(h.level).toBe("short");
    expect(h.nightsLeft).toBe(3);
    expect(h.sentence).toContain("3 more nights");
    expect(h.reclaimHint).toContain("8.0 GB");
    expect(h.reclaimHint).toContain("safe thing to clear");
  });

  it("uses singular grammar for one night", () => {
    const h = storageHeadroom({
      freeBytes: 1.5 * GB,
      nightlyBytes: 1 * GB, // floor → 1 night
      reclaimableCacheBytes: 0,
    });
    expect(h.level).toBe("short");
    expect(h.nightsLeft).toBe(1);
    expect(h.sentence).toContain("1 more night");
    expect(h.sentence).not.toContain("1 more nights");
    // No cache to reclaim → no hint even though it's short.
    expect(h.reclaimHint).toBeNull();
  });

  it("reads almost-full when there is under a night left", () => {
    const h = storageHeadroom({
      freeBytes: 0.4 * GB,
      nightlyBytes: 1 * GB,
      reclaimableCacheBytes: 2 * GB,
    });
    expect(h.level).toBe("short");
    expect(h.nightsLeft).toBe(0);
    expect(h.sentence).toContain("Almost out of space");
    expect(h.reclaimHint).toContain("2.0 GB");
  });

  it("falls back to just the free figure when history is too thin", () => {
    const h = storageHeadroom({
      freeBytes: 42 * GB,
      nightlyBytes: null,
      reclaimableCacheBytes: 3 * GB,
    });
    expect(h.level).toBe("unknown");
    expect(h.nightsLeft).toBeNull();
    expect(h.sentence).toContain("42 GB free");
    expect(h.sentence).toContain("not enough imaging history");
    expect(h.reclaimHint).toBeNull();
  });

  it("treats a zero or negative rate as unknown, not infinite nights", () => {
    const h = storageHeadroom({
      freeBytes: 10 * GB,
      nightlyBytes: 0,
      reclaimableCacheBytes: 0,
    });
    expect(h.level).toBe("unknown");
    expect(h.nightsLeft).toBeNull();
  });

  it("reports when the free space is unreadable", () => {
    const h = storageHeadroom({
      freeBytes: null,
      nightlyBytes: 5 * GB,
      reclaimableCacheBytes: 0,
    });
    expect(h.level).toBe("unknown");
    expect(h.sentence).toContain("Couldn't read");
  });
});
