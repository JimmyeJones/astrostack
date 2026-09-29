import { describe, expect, it } from "vitest";

import { skyMotion, starfieldShown, surroundForPath } from "./surround";

describe("which routes get the sky", () => {
  it("gives the ordinary pages the sky", () => {
    for (const path of ["/", "", "/library", "/targets/M_42", "/targets/M_42/stack",
      "/targets/M_42/history", "/settings", "/settings/telescope", "/jobs", "/gallery",
      "/sky-so-far", "/sky-so-far/2026"]) {
      expect(surroundForPath(path), path).toBe("sky");
    }
  });

  it("keeps a neutral surround wherever a picture is being judged", () => {
    // A tint shifts how colour and background level are perceived — the reason
    // PixInsight and Photoshop surround an image with neutral grey.
    expect(surroundForPath("/targets/M_42/edit/17")).toBe("neutral");
    expect(surroundForPath("/targets/NGC_6888_mosaic/edit/3")).toBe("neutral");
    expect(surroundForPath("/compare")).toBe("neutral");
  });

  it("keeps a neutral surround on the two routes that draw their own sky", () => {
    expect(surroundForPath("/sky")).toBe("neutral");
    expect(surroundForPath("/universe")).toBe("neutral");
  });

  it("does not let a neutral name swallow a neighbouring route", () => {
    // `/sky` is neutral; `/sky-so-far` is a gallery of the user's own pictures
    // and is not, which a bare `startsWith` would get wrong.
    expect(surroundForPath("/sky-so-far")).toBe("sky");
    expect(surroundForPath("/compare-notes")).toBe("sky");
    // ...and a target whose name merely contains "edit" is not the editor.
    expect(surroundForPath("/targets/edit")).toBe("sky");
  });

  it("ignores a trailing slash", () => {
    expect(surroundForPath("/compare/")).toBe("neutral");
    expect(surroundForPath("/library/")).toBe("sky");
  });
});

describe("when the stars are drawn at all", () => {
  it("needs both the sky and this device's opt-in", () => {
    expect(starfieldShown("sky", true)).toBe(true);
    expect(starfieldShown("sky", false)).toBe(false);
    // Turning the stars on cannot put them behind the editor's picture.
    expect(starfieldShown("neutral", true)).toBe(false);
    expect(starfieldShown("neutral", false)).toBe(false);
  });
});

describe("when the stars move", () => {
  it("drifts only when nothing asks it not to", () => {
    expect(skyMotion(false, false)).toBe("drifting");
  });
  it("holds still for reduced motion, and for a tab nobody is looking at", () => {
    expect(skyMotion(true, false)).toBe("still");
    expect(skyMotion(false, true)).toBe("still");
    expect(skyMotion(true, true)).toBe("still");
  });
});
