import { afterEach, describe, expect, it, vi } from "vitest";

import { STARFIELD_PREF_EVENT, isStarfieldEnabled, setStarfieldEnabled } from "./prefs";

const KEY = "astrostack.nightsky.starfield";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

describe("the starfield opt-out", () => {
  it("is ON on a fresh device — it is what the app is meant to look like", () => {
    expect(isStarfieldEnabled()).toBe(true);
  });

  it("round-trips off and on, storing only the opt-out", () => {
    setStarfieldEnabled(false);
    expect(isStarfieldEnabled()).toBe(false);
    expect(localStorage.getItem(KEY)).toBe("0");

    setStarfieldEnabled(true);
    expect(isStarfieldEnabled()).toBe(true);
    // Back to the default clears the key rather than storing a second truthy
    // spelling of it, so there is exactly one way to say "on".
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("reads as ON — never throws into the app shell — when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(isStarfieldEnabled()).toBe(true);
  });

  it("swallows a throwing write, and still announces the change", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    const heard = vi.fn();
    window.addEventListener(STARFIELD_PREF_EVENT, heard);
    expect(() => setStarfieldEnabled(false)).not.toThrow();
    // The preference could not persist, but the switch must still do something
    // visible for as long as this page lives.
    expect(heard).toHaveBeenCalledTimes(1);
    window.removeEventListener(STARFIELD_PREF_EVENT, heard);
  });

  it("announces every change on the window, so a mounted sky can react", () => {
    const heard = vi.fn();
    window.addEventListener(STARFIELD_PREF_EVENT, heard);
    setStarfieldEnabled(false);
    setStarfieldEnabled(true);
    expect(heard).toHaveBeenCalledTimes(2);
    window.removeEventListener(STARFIELD_PREF_EVENT, heard);
  });

  it("treats a hand-edited value that is not the opt-out as on", () => {
    localStorage.setItem(KEY, "yes please");
    expect(isStarfieldEnabled()).toBe(true);
  });
});
