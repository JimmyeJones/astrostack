import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_VOLUME,
  ambientVolume,
  isAmbientEnabled,
  setAmbientEnabled,
  setAmbientVolume,
} from "./prefs";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("the ambient opt-in", () => {
  it("is off on a fresh install — a new box must be silent", () => {
    expect(isAmbientEnabled()).toBe(false);
  });
  it("round-trips on and off", () => {
    setAmbientEnabled(true);
    expect(isAmbientEnabled()).toBe(true);
    setAmbientEnabled(false);
    expect(isAmbientEnabled()).toBe(false);
    // Off clears the key rather than storing a falsy string.
    expect(localStorage.getItem("astrostack.ambient.enabled")).toBeNull();
  });
  it("reads as off — never crashes the shell — when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(isAmbientEnabled()).toBe(false);
  });
  it("survives a write to a full or disabled store", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceeded");
    });
    expect(() => setAmbientEnabled(true)).not.toThrow();
  });
});

describe("the ambient volume", () => {
  it("defaults to a background level when never set", () => {
    expect(ambientVolume()).toBe(DEFAULT_VOLUME);
    expect(DEFAULT_VOLUME).toBeGreaterThan(0);
    expect(DEFAULT_VOLUME).toBeLessThan(1);
  });
  it("round-trips a chosen level", () => {
    setAmbientVolume(0.25);
    expect(ambientVolume()).toBeCloseTo(0.25, 6);
  });
  it("clamps a nonsense level into range on the way in", () => {
    setAmbientVolume(4);
    expect(ambientVolume()).toBe(1);
    setAmbientVolume(-2);
    expect(ambientVolume()).toBe(0);
    setAmbientVolume(NaN);
    expect(ambientVolume()).toBe(DEFAULT_VOLUME);
  });
  it("falls back to the default for a hand-edited/garbage stored value", () => {
    localStorage.setItem("astrostack.ambient.volume", "loud");
    expect(ambientVolume()).toBe(DEFAULT_VOLUME);
    localStorage.setItem("astrostack.ambient.volume", "");
    expect(ambientVolume()).toBe(DEFAULT_VOLUME);
    localStorage.setItem("astrostack.ambient.volume", "7");
    expect(ambientVolume()).toBe(DEFAULT_VOLUME);
  });
});
