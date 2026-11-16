import { describe, expect, it } from "vitest";
import { keyBelongsElsewhere, lightboxNeighbours, swipeStep, SWIPE_MIN_PX } from "./lightboxNav";

const same = (a: { id: number }, b: { id: number }) => a.id === b.id;
const list = [{ id: 1 }, { id: 2 }, { id: 3 }];

describe("lightboxNeighbours", () => {
  it("names the neighbours and the position in the middle of the list", () => {
    expect(lightboxNeighbours(list, { id: 2 }, same)).toEqual({
      prev: { id: 1 }, next: { id: 3 }, position: "2 of 3",
    });
  });

  it("stops at the ends rather than wrapping", () => {
    expect(lightboxNeighbours(list, { id: 1 }, same)?.prev).toBeNull();
    expect(lightboxNeighbours(list, { id: 3 }, same)?.next).toBeNull();
  });

  it("matches by identity, not object reference", () => {
    // A refetch hands back new objects for the same pictures.
    expect(lightboxNeighbours(list, { id: 3 }, same)?.position).toBe("3 of 3");
  });

  it("offers nothing for a lone picture, a closed viewer or one no longer listed", () => {
    expect(lightboxNeighbours([{ id: 1 }], { id: 1 }, same)).toBeNull();
    expect(lightboxNeighbours(list, null, same)).toBeNull();
    expect(lightboxNeighbours(list, { id: 9 }, same)).toBeNull();
  });
});

describe("swipeStep", () => {
  it("a flick left is next, a flick right is previous", () => {
    expect(swipeStep(-120, 10)).toBe(1);
    expect(swipeStep(120, -10)).toBe(-1);
  });

  it("a short or mostly vertical movement is not a swipe", () => {
    expect(swipeStep(SWIPE_MIN_PX - 1, 0)).toBe(0);
    expect(swipeStep(-100, 80)).toBe(0);
    expect(swipeStep(0, 0)).toBe(0);
    expect(swipeStep(Number.NaN, 0)).toBe(0);
  });
});

describe("keyBelongsElsewhere", () => {
  it("leaves the arrows to text fields and open menus", () => {
    const input = document.createElement("input");
    const menu = document.createElement("div");
    menu.setAttribute("role", "menu");
    const item = document.createElement("button");
    menu.appendChild(item);
    expect(keyBelongsElsewhere(input)).toBe(true);
    expect(keyBelongsElsewhere(item)).toBe(true);
  });

  it("takes the arrows everywhere else", () => {
    expect(keyBelongsElsewhere(document.body)).toBe(false);
    expect(keyBelongsElsewhere(null)).toBe(false);
  });
});
