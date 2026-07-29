import { describe, expect, it } from "vitest";
import { isNavActive } from "./navActive";

describe("isNavActive", () => {
  it("does not double-highlight a shared prefix that is not a segment boundary", () => {
    // The bug: on /sky-so-far, both "Your sky, so far" (/sky-so-far) and
    // "Sky Map" (/sky) lit up because /sky-so-far.startsWith("/sky").
    expect(isNavActive("/sky-so-far", "/sky-so-far")).toBe(true);
    expect(isNavActive("/sky-so-far", "/sky")).toBe(false);
  });

  it("matches an exact path", () => {
    expect(isNavActive("/library", "/library")).toBe(true);
    expect(isNavActive("/gallery", "/library")).toBe(false);
  });

  it("matches a real sub-route (segment boundary)", () => {
    expect(isNavActive("/library/M31", "/library")).toBe(true);
    expect(isNavActive("/tonight/anything", "/tonight")).toBe(true);
  });

  it("handles the Dashboard end-anchored root link", () => {
    expect(isNavActive("/", "/", true)).toBe(true);
    expect(isNavActive("/library", "/", true)).toBe(false);
  });
});
