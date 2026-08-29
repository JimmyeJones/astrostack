import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  AnnotatedImage,
  compassLayout,
  croppedAnnotationView,
  objectLabel,
  deconflictMarkers,
  labelBudget,
  objectMarkerLayout,
  scaleBarLayout,
} from "./AnnotatedImage";
import type { FieldObject, ScaleBar } from "../api/client";

function obj(over: Partial<FieldObject> = {}): FieldObject {
  return {
    catalog_id: "M31", name: "Andromeda Galaxy", type: "galaxy",
    ra_deg: 10.68, dec_deg: 41.27, x_px: 500, y_px: 300, ...over,
  };
}

describe("objectMarkerLayout", () => {
  it("maps FITS pixel coords into a same-aspect box (no letterbox)", () => {
    // 1000×600 image into a 500×300 box → uniform 0.5 scale, no offset.
    const m = objectMarkerLayout([obj({ x_px: 500, y_px: 300 })], 1000, 600, 500, 300);
    expect(m).toHaveLength(1);
    expect(m[0].left).toBeCloseTo(250);
    expect(m[0].top).toBeCloseTo(150);
    expect(m[0].visible).toBe(true);
  });

  it("accounts for letterboxing when the box aspect differs (contain fit)", () => {
    // 1000×500 image (2:1) into a 400×400 box → scale 0.4, rendered 400×200,
    // centred with a 100px top/bottom letterbox.
    const m = objectMarkerLayout([obj({ x_px: 0, y_px: 0 })], 1000, 500, 400, 400);
    expect(m[0].left).toBeCloseTo(0);
    expect(m[0].top).toBeCloseTo(100); // top-left of the image sits 100px down
    expect(m[0].visible).toBe(true);
  });

  it("flags an object whose centre lands outside the rendered image", () => {
    // A marker far past the image bounds is not visible.
    const m = objectMarkerLayout([obj({ x_px: 2000, y_px: 300 })], 1000, 600, 500, 300);
    expect(m[0].visible).toBe(false);
  });

  it("returns nothing until every dimension is known", () => {
    expect(objectMarkerLayout([obj()], 1000, 600, 0, 300)).toEqual([]);
    expect(objectMarkerLayout([obj()], 0, 600, 500, 300)).toEqual([]);
  });
});

describe("deconflictMarkers", () => {
  // A field where several objects project to nearly the same spot — the Sword of
  // Orion case: on a 260px card their chips would land within a few pixels of
  // each other and overlap into mush.
  const crowded = (n: number) =>
    Array.from({ length: n }, (_, i) =>
      obj({ catalog_id: `NGC${100 + i}`, name: `Object ${i}`,
        x_px: 500 + i * 4, y_px: 300 + i * 3 }));

  const place = (objects: FieldObject[], boxW = 600, boxH = 260) =>
    deconflictMarkers(
      objectMarkerLayout(objects, 1000, 600, boxW, boxH), boxW, boxH);

  it("gives every chip a spot of its own", () => {
    const placed = place(crowded(5));
    const rects = placed.map((m) => {
      const w = objectLabel(m.object).length * 6.2 + 10;
      return {
        x0: m.left + m.labelDx - w / 2, x1: m.left + m.labelDx + w / 2,
        y0: m.top + m.labelDy - 7.5, y1: m.top + m.labelDy + 7.5,
      };
    });
    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i];
        const b = rects[j];
        const apart = a.x1 <= b.x0 || b.x1 <= a.x0 || a.y1 <= b.y0 || b.y1 <= a.y0;
        expect(apart).toBe(true);
      }
    }
  });

  it("is what the old behaviour was not — pinned against it", () => {
    // Before this, every chip sat dead-centre on its object, so five objects a
    // few pixels apart produced five mutually overlapping chips.
    const raw = objectMarkerLayout(crowded(5), 1000, 600, 600, 260);
    const spread = Math.max(...raw.map((m) => m.left)) - Math.min(...raw.map((m) => m.left));
    expect(spread).toBeLessThan(20);          // they really are on top of each other
    const placed = place(crowded(5));
    const offsets = new Set(placed.map((m) => `${m.labelDx},${m.labelDy}`));
    expect(offsets.size).toBe(placed.length); // …and now each has its own place
  });

  it("never moves a dot — only its chip", () => {
    const raw = objectMarkerLayout(crowded(4), 1000, 600, 600, 260);
    const placed = place(crowded(4));
    for (const m of placed) {
      const original = raw.find((r) => r.object.catalog_id === m.object.catalog_id)!;
      expect(m.left).toBe(original.left);
      expect(m.top).toBe(original.top);
    }
  });

  it("keeps the labels nearest the centre when it can't keep them all", () => {
    // 30 objects piled around the centre, far past any box's budget.
    const many = Array.from({ length: 30 }, (_, i) =>
      obj({ catalog_id: `NGC${i}`, name: `O${i}`, x_px: 500 + i, y_px: 300 + i }));
    const placed = place(many);
    expect(placed.length).toBeLessThan(many.length);
    const kept = placed.map((m) => m.r);
    const dropped = objectMarkerLayout(many, 1000, 600, 600, 260)
      .filter((m) => !placed.some((p) => p.object.catalog_id === m.object.catalog_id))
      .map((m) => m.r);
    expect(Math.max(...kept)).toBeLessThanOrEqual(Math.min(...dropped));
  });

  it("orders notability exactly as the read-out under the picture does", () => {
    // `describeFieldObjects` sorts on normalised distance from the centre; the
    // labels must agree, or the picture and the list disagree about what matters.
    const m = objectMarkerLayout(
      [obj({ x_px: 500, y_px: 300 }), obj({ catalog_id: "X", x_px: 900, y_px: 550 })],
      1000, 600, 600, 260);
    expect(m[0].r).toBeCloseTo(0);
    expect(m[1].r).toBeGreaterThan(m[0].r);
  });

  it("draws more labels on a bigger box and few on a small card", () => {
    expect(labelBudget(180, 120)).toBe(3);        // floor: always at least a few
    expect(labelBudget(600, 180)).toBeLessThan(labelBudget(600, 400));
    expect(labelBudget(2000, 1200)).toBe(12);     // ceiling: never a wall of text
    expect(labelBudget(0, 300)).toBe(0);
  });

  it("keeps every chip inside the box", () => {
    // Objects hard against each edge: a chip must never hang off the picture.
    const edges = [
      obj({ catalog_id: "TL", name: "Top left", x_px: 2, y_px: 2 }),
      obj({ catalog_id: "BR", name: "Bottom right", x_px: 998, y_px: 598 }),
    ];
    for (const m of place(edges)) {
      const w = objectLabel(m.object).length * 6.2 + 10;
      expect(m.left + m.labelDx - w / 2).toBeGreaterThanOrEqual(0);
      expect(m.top + m.labelDy - 7.5).toBeGreaterThanOrEqual(0);
      expect(m.left + m.labelDx + w / 2).toBeLessThanOrEqual(600);
      expect(m.top + m.labelDy + 7.5).toBeLessThanOrEqual(260);
    }
  });

  it("drops an off-picture object and copes with an unmeasured box", () => {
    expect(place([obj({ x_px: 5000, y_px: 300 })])).toEqual([]);
    expect(deconflictMarkers([], 0, 0)).toEqual([]);
  });

  it("labels an ordinary sparse field with no nudging beyond the first choice", () => {
    // The common case must not get worse: three well-separated objects each keep
    // the natural "chip under the dot" placement.
    const placed = place([
      obj({ catalog_id: "A", name: "A", x_px: 200, y_px: 150 }),
      obj({ catalog_id: "B", name: "B", x_px: 500, y_px: 300 }),
      obj({ catalog_id: "C", name: "C", x_px: 800, y_px: 450 }),
    ]);
    expect(placed).toHaveLength(3);
    expect(placed.every((m) => m.labelDx === 0)).toBe(true);
  });
});

describe("scaleBarLayout", () => {
  const bar: ScaleBar = {
    arcsec: 1800, label: "30′", fraction: 0.2, frame_arcmin: 150,
    moon_comparison: "the whole frame is about 5.0 full Moons wide",
  };

  it("scales the bar to a fraction of the rendered (contain-fit) width", () => {
    // 1000×600 image in a 500×300 box → scale 0.5 → renderW 500 → bar 0.2·500=100.
    expect(scaleBarLayout(bar, 1000, 600, 500, 300)).toEqual({ widthPx: 100 });
  });

  it("uses the letterbox-limited width when the box is a different aspect", () => {
    // 1000×600 in a 1000×300 box → limited by height (0.5) → renderW 500 → 100.
    expect(scaleBarLayout(bar, 1000, 600, 1000, 300)).toEqual({ widthPx: 100 });
  });

  it("returns null when there is no bar or the box is unmeasured", () => {
    expect(scaleBarLayout(null, 1000, 600, 500, 300)).toBeNull();
    expect(scaleBarLayout(bar, 1000, 600, 0, 300)).toBeNull();
    expect(scaleBarLayout({ ...bar, fraction: 0 }, 1000, 600, 500, 300)).toBeNull();
  });
});

describe("objectLabel", () => {
  it("prefers the friendly name, falls back to the catalog id", () => {
    expect(objectLabel(obj({ name: "Andromeda Galaxy" }))).toBe("Andromeda Galaxy");
    expect(objectLabel(obj({ name: "" }))).toBe("M31");
    expect(objectLabel(obj({ name: "   " }))).toBe("M31");
  });
});

function renderImg(show: boolean) {
  return render(
    <MantineProvider>
      <AnnotatedImage
        src="/preview.png" alt="M31" imgWidth={1000} imgHeight={600}
        objects={[obj()]} show={show} height={180}
      />
    </MantineProvider>,
  );
}

describe("AnnotatedImage", () => {
  it("renders the image bare when markers are off", () => {
    renderImg(false);
    expect(screen.getByAltText("M31")).toBeInTheDocument();
    expect(screen.queryByTestId("object-marker")).toBeNull();
  });

  it("does not throw when asked to show markers (box measured to 0 in jsdom)", () => {
    // jsdom reports clientWidth/Height as 0, so no marker is placed — but the
    // component must render without error and still show the image.
    renderImg(true);
    expect(screen.getByAltText("M31")).toBeInTheDocument();
  });
});

describe("croppedAnnotationView", () => {
  const bar: ScaleBar = {
    arcsec: 60, label: "1′", fraction: 0.2, frame_arcmin: 5,
    moon_comparison: "about a fifth of a full Moon wide",
  };

  it("leaves an ordinary (un-cropped) run exactly as it is", () => {
    const objs = [obj({ x_px: 500, y_px: 300 })];
    const v = croppedAnnotationView(null, objs, bar, 1000, 600);
    expect(v.objects).toBe(objs);
    expect(v.scaleBar).toBe(bar);
    expect(v.width).toBe(1000);
    expect(v.height).toBe(600);
  });

  it("shifts object pins into the trimmed picture", () => {
    // The auto-edit kept x 200…800, y 60…540 of a 1000×600 canvas.
    const v = croppedAnnotationView(
      { x0: 0.2, y0: 0.1, x1: 0.8, y1: 0.9 },
      [obj({ x_px: 500, y_px: 300 })], null, 1000, 600);
    expect(v.width).toBe(600);
    expect(v.height).toBe(480);
    expect(v.objects[0].x_px).toBe(300);   // 500 − 200
    expect(v.objects[0].y_px).toBe(240);   // 300 − 60
  });

  it("drops an object the trim cut away", () => {
    const v = croppedAnnotationView(
      { x0: 0.5, y0: 0.0, x1: 1.0, y1: 1.0 },
      [obj({ x_px: 100, y_px: 300 }), obj({ catalog_id: "M32", x_px: 900, y_px: 300 })],
      null, 1000, 600);
    expect(v.objects.map((o) => o.catalog_id)).toEqual(["M32"]);
  });

  it("re-bases the scale bar on the narrower picture", () => {
    // Half the width kept → the same on-sky bar covers twice the share.
    const v = croppedAnnotationView(
      { x0: 0.25, y0: 0.0, x1: 0.75, y1: 1.0 }, [], bar, 1000, 600);
    expect(v.scaleBar?.fraction).toBeCloseTo(0.4);
    expect(v.scaleBar?.label).toBe("1′");   // the bar's own length is unchanged
  });

  it("drops a bar that would no longer fit on the picture", () => {
    const v = croppedAnnotationView(
      { x0: 0.45, y0: 0.0, x1: 0.55, y1: 1.0 }, [], bar, 1000, 600);
    expect(v.scaleBar).toBeNull();          // 0.2 × 10 = 2× the picture width
  });

  it("is a no-op for a full-canvas crop or an unknown size", () => {
    const objs = [obj()];
    expect(croppedAnnotationView({ x0: 0, y0: 0, x1: 1, y1: 1 }, objs, bar, 1000, 600)
      .objects).toBe(objs);
    expect(croppedAnnotationView({ x0: 0.2, y0: 0, x1: 0.8, y1: 1 }, objs, bar, 0, 0)
      .objects).toBe(objs);
  });
});

// "Which way is up?" — the on-screen half of the North/East rose the shared JPEG
// has baked since v0.284.0. Angles come off the engine's own convention
// (`seestack.skymarks`): degrees counter-clockwise from screen-right, screen-up
// positive, so North-is-up is 90. CSS y grows downward, so every arm's screen
// vector negates the y component — the sign error that would silently draw the
// sky upside down, which is why these assert the direction and not just a length.
describe("compassLayout", () => {
  it("points North straight up on an already-North-up field", () => {
    const c = compassLayout({ north_deg: 90, east_deg: 180 }, 400, 300)!;
    expect(c.north.dx).toBeCloseTo(0);
    expect(c.north.dy).toBeCloseTo(-c.armPx);   // up on screen is negative y
    expect(c.east.dx).toBeCloseTo(-c.armPx);    // East to the left: the usual
    expect(c.east.dy).toBeCloseTo(0);           // sky parity for a normal field
  });

  it("turns both arms with a rotated field", () => {
    // A field rotated so North points screen-right (0°) and East points down.
    const c = compassLayout({ north_deg: 0, east_deg: -90 }, 400, 300)!;
    expect(c.north.dx).toBeCloseTo(c.armPx);
    expect(c.north.dy).toBeCloseTo(0);
    expect(c.east.dx).toBeCloseTo(0);
    expect(c.east.dy).toBeCloseTo(c.armPx);
  });

  it("draws a mirrored field mirrored, because that is what the WCS says", () => {
    // Negative parity: East ends up 90° clockwise of North rather than CCW.
    const c = compassLayout({ north_deg: 90, east_deg: 0 }, 400, 300)!;
    expect(c.north.dy).toBeCloseTo(-c.armPx);
    expect(c.east.dx).toBeCloseTo(c.armPx);
  });

  it("sizes the arms off the box's short side, so a wide box isn't overdrawn", () => {
    const wide = compassLayout({ north_deg: 90, east_deg: 180 }, 1200, 300)!;
    const square = compassLayout({ north_deg: 90, east_deg: 180 }, 300, 300)!;
    expect(wide.armPx).toBe(square.armPx);
    expect(wide.armPx).toBeLessThan(300 / 2);   // can't span the picture
  });

  it("places nothing when there is nothing to place", () => {
    expect(compassLayout(null, 400, 300)).toBeNull();
    expect(compassLayout(undefined, 400, 300)).toBeNull();
    expect(compassLayout({ north_deg: 90, east_deg: 180 }, 0, 300)).toBeNull();
    expect(compassLayout({ north_deg: 90, east_deg: 180 }, 400, 0)).toBeNull();
  });

  it("refuses a non-finite angle rather than drawing a NaN arm", () => {
    expect(compassLayout({ north_deg: NaN, east_deg: 180 }, 400, 300)).toBeNull();
    expect(compassLayout({ north_deg: 90, east_deg: Infinity }, 400, 300)).toBeNull();
  });
});

describe("AnnotatedImage — the rose", () => {
  function renderRose(showCompass: boolean) {
    return render(
      <MantineProvider>
        <AnnotatedImage
          src="/preview.png" alt="M31" imgWidth={1000} imgHeight={600}
          objects={[]} show={false} height={180}
          directions={{ north_deg: 90, east_deg: 180 }} showCompass={showCompass}
        />
      </MantineProvider>,
    );
  }

  it("draws no rose until it is asked for", () => {
    renderRose(false);
    expect(screen.queryByTestId("sky-compass")).toBeNull();
    expect(screen.getByAltText("M31")).toBeInTheDocument();
  });

  it("does not throw when asked for one (box measured to 0 in jsdom)", () => {
    // Same jsdom limitation the marker/scale-bar cases have: clientWidth is 0, so
    // nothing is placed — the geometry is covered by compassLayout's unit tests.
    renderRose(true);
    expect(screen.getByAltText("M31")).toBeInTheDocument();
  });
});

describe("AnnotatedImage — the overlay layer", () => {
  function renderOverlay(overlaySrc: string | null) {
    return render(
      <MantineProvider>
        <AnnotatedImage
          src="/preview.png" alt="M31" imgWidth={1000} imgHeight={600}
          objects={[]} show={false} height={180} overlaySrc={overlaySrc}
        />
      </MantineProvider>,
    );
  }

  it("draws nothing over the picture by default", () => {
    renderOverlay(null);
    expect(screen.queryByTestId("image-overlay")).toBeNull();
    expect(screen.getByAltText("M31")).toBeInTheDocument();
  });

  it("lays the overlay on the picture's own contain-fit grid", () => {
    // The overlay PNG is the same pixel size as the picture, so sharing the
    // contain-fit is what makes it land true at any box size — a different fit
    // would slide the highlighted trail off the trail.
    renderOverlay("/rej.png");
    const overlay = screen.getByTestId("image-overlay");
    expect(overlay).toHaveAttribute("src", "/rej.png");
    expect(overlay.style.objectFit).toBe("contain");
    expect(overlay.style.position).toBe("absolute");
    // Decorative and click-through: the picture underneath still opens the
    // lightbox, and a screen reader isn't told about a tint it can't see.
    expect(overlay.style.pointerEvents).toBe("none");
    expect(overlay).toHaveAttribute("aria-hidden");
  });
});
