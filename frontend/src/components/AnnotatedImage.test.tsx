import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnnotatedImage, objectLabel, objectMarkerLayout, scaleBarLayout } from "./AnnotatedImage";
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
