import { describe, expect, it } from "vitest";
import { clickFraction, loupeCaption, loupeMarkerRect, loupeWhereText } from "./loupe";

describe("loupeMarkerRect", () => {
  it("draws the window as its true share of the picture", () => {
    // A 512 px window on a 4096 px-wide picture is an eighth of it — which is the
    // whole reason the marker exists: at that scale a beginner otherwise has no
    // idea which scrap of sky they are inspecting.
    const r = loupeMarkerRect(0.5, 0.5, 512, 4096, 2048)!;
    expect(r.width).toBeCloseTo(12.5);
    expect(r.height).toBeCloseTo(25);
    expect(r.left).toBeCloseTo(50 - 12.5 / 2);
    expect(r.top).toBeCloseTo(50 - 25 / 2);
  });

  it("stays inside the box at the edges, as the server clamps its window", () => {
    const tl = loupeMarkerRect(0, 0, 512, 4096, 2048)!;
    expect(tl.left).toBe(0);
    expect(tl.top).toBe(0);
    const br = loupeMarkerRect(1, 1, 512, 4096, 2048)!;
    expect(br.left + br.width).toBeCloseTo(100);
    expect(br.top + br.height).toBeCloseTo(100);
  });

  it("draws the whole box when the window is bigger than the picture", () => {
    const r = loupeMarkerRect(0.5, 0.5, 512, 300, 200)!;
    expect(r).toEqual({ left: 0, top: 0, width: 100, height: 100 });
  });

  it("is null until the preview's size in source pixels is known", () => {
    expect(loupeMarkerRect(0.5, 0.5, 512, null, 2048)).toBeNull();
    expect(loupeMarkerRect(0.5, 0.5, 512, 4096, undefined)).toBeNull();
    expect(loupeMarkerRect(0.5, 0.5, 0, 4096, 2048)).toBeNull();
    expect(loupeMarkerRect(0.5, 0.5, 512, Number.NaN, 2048)).toBeNull();
  });

  it("treats a non-finite click as the centre rather than flying off", () => {
    const r = loupeMarkerRect(Number.NaN, Number.NaN, 512, 4096, 2048)!;
    expect(r.left).toBeCloseTo(50 - 12.5 / 2);
  });
});

describe("clickFraction", () => {
  const box = { left: 100, top: 50, width: 200, height: 100 };

  it("reports where in the preview the tap landed", () => {
    expect(clickFraction(150, 75, box)).toEqual({ fx: 0.25, fy: 0.25 });
    expect(clickFraction(300, 150, box)).toEqual({ fx: 1, fy: 1 });
  });

  it("clamps a tap on the very border, and survives a zero-size box", () => {
    expect(clickFraction(0, 0, box)).toEqual({ fx: 0, fy: 0 });
    expect(clickFraction(9999, 9999, box)).toEqual({ fx: 1, fy: 1 });
    expect(clickFraction(10, 10, { left: 0, top: 0, width: 0, height: 0 }))
      .toEqual({ fx: 0.5, fy: 0.5 });
  });
});

describe("loupeCaption", () => {
  it("says what it is in words a beginner uses, not '1:1'", () => {
    const s = loupeCaption(512, 8);
    expect(s).toContain("512 × 512");
    expect(s).toContain("full size");
    expect(s).toContain("8th of full size");
    expect(s).not.toMatch(/decimat|proxy|1:1/i);
  });

  it("drops the shrunk-preview clause when there is no shrinking", () => {
    expect(loupeCaption(512, 1)).not.toContain("shrunk");
    expect(loupeCaption(512, null)).not.toContain("shrunk");
  });
});

describe("loupeWhereText", () => {
  const win = (x: number, y: number, size = 512) => ({
    x, y, width: size, height: size, canvas_width: 6000, canvas_height: 4000,
  });

  it("names the corner a window sits in, from the server's own rectangle", () => {
    expect(loupeWhereText(win(0, 0))).toBe("This is the top-left of your picture.");
    expect(loupeWhereText(win(5488, 3488)))
      .toBe("This is the bottom-right of your picture.");
  });

  it("says 'the middle' when it really is the middle", () => {
    // Thirds, not halves: a centred window must not be called "the left".
    expect(loupeWhereText(win(2744, 1744))).toBe("This is the middle of your picture.");
  });

  it("drops the redundant half of an edge that is centred on the other axis", () => {
    expect(loupeWhereText(win(2744, 0))).toBe("This is the top of your picture.");
    expect(loupeWhereText(win(0, 1744))).toBe("This is the left of your picture.");
  });

  it("says nothing when there is no 'where' to name", () => {
    expect(loupeWhereText(null)).toBeNull();
    expect(loupeWhereText(undefined)).toBeNull();
    // The window covers the whole canvas — "all of it" is obvious from the picture.
    expect(loupeWhereText({
      x: 0, y: 0, width: 400, height: 300, canvas_width: 400, canvas_height: 300,
    })).toBeNull();
  });

  it("stays quiet on nonsense rather than naming a corner from a NaN", () => {
    expect(loupeWhereText({ ...win(0, 0), canvas_width: 0 })).toBeNull();
    expect(loupeWhereText({ ...win(0, 0), x: Number.NaN })).toBeNull();
    expect(loupeWhereText({ ...win(0, 0), width: 0 })).toBeNull();
  });
});
