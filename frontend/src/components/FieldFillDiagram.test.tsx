import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FieldFillDiagram, fieldFillGeometry } from "./FieldFillDiagram";
import type { FieldFill } from "../api/client";

// An S30's single frame, the field the owner's own solved subs derive.
const S30 = { field_long_arcmin: 128, field_short_arcmin: 72 };

function fill(frac_long: number, frac_short: number, text = "x"): FieldFill {
  return { ...S30, frac_long, frac_short, text };
}

function renderDiagram(f: FieldFill) {
  return render(
    <MantineProvider>
      <FieldFillDiagram fill={f} name="M 42" />
    </MantineProvider>,
  );
}

describe("fieldFillGeometry", () => {
  it("scales the object's box with the size/field ratio", () => {
    // The one thing the picture claims: half the frame's width is drawn half
    // the frame's width. Both axes, independently.
    const half = fieldFillGeometry(fill(0.5, 0.5))!;
    expect(half.object.rx / half.frame.w).toBeCloseTo(0.25, 6);
    expect(half.object.ry / half.frame.h).toBeCloseTo(0.25, 6);

    const quarter = fieldFillGeometry(fill(0.25, 0.25))!;
    expect(quarter.object.rx).toBeCloseTo(half.object.rx / 2, 6);
    // …and the frame itself does not move when the object shrinks.
    expect(quarter.frame).toEqual(half.frame);
  });

  it("draws the frame in the field's own shape, not a fixed rectangle", () => {
    const g = fieldFillGeometry(fill(0.5, 0.5))!;
    expect(g.frame.w / g.frame.h).toBeCloseTo(128 / 72, 6);
    // A different telescope gives a differently-shaped frame from the same
    // fractions — the field rides along precisely so this can't be assumed.
    const s50 = fieldFillGeometry({
      frac_long: 0.5, frac_short: 0.5, text: "x",
      field_long_arcmin: 77, field_short_arcmin: 44,
    })!;
    expect(s50.frame.w / s50.frame.h).toBeCloseTo(77 / 44, 6);
  });

  it("grows the viewport for an object that overflows, never clipping it", () => {
    // The overflow is the single most useful thing the picture says, so a
    // too-big object must still be drawn whole — the viewport widens instead.
    const g = fieldFillGeometry(fill(2, 2))!;
    expect(g.object.rx * 2).toBeGreaterThan(g.frame.w);
    const [x, y, w, h] = g.viewBox.split(" ").map(Number);
    expect(w).toBeGreaterThan(g.object.rx * 2);
    expect(h).toBeGreaterThan(g.object.ry * 2);
    // Centred: the object sits in the middle of the viewport it asked for.
    expect(x + w / 2).toBeCloseTo(0, 6);
    expect(y + h / 2).toBeCloseTo(0, 6);
  });

  it("keeps the rendered height in step with the content's own aspect", () => {
    const wide = fieldFillGeometry(fill(0.2, 0.2), { width: 200 })!;
    expect(wide.width).toBe(200);
    // The padding is proportional on each axis, so the drawn box keeps the
    // frame's own shape (to within the pixel rounding).
    expect(Math.abs(wide.height - 200 * (72 / 128))).toBeLessThanOrEqual(1);
    // A tall overflow makes the drawing taller rather than squashing the frame.
    const tall = fieldFillGeometry(fill(0.2, 4), { width: 200 })!;
    expect(tall.height).toBeGreaterThan(wide.height);
  });

  it("declines a degenerate field rather than dividing by it", () => {
    expect(fieldFillGeometry({
      frac_long: 0.5, frac_short: 0.5, text: "x",
      field_long_arcmin: 0, field_short_arcmin: 72,
    })).toBeNull();
    expect(fieldFillGeometry({
      frac_long: Number.NaN, frac_short: 0.5, text: "x", ...S30,
    })).toBeNull();
  });
});

describe("FieldFillDiagram", () => {
  it("renders the backend's sentence beside the picture", () => {
    // The words and the picture come off one payload, so they cannot disagree —
    // the component never phrases its own verdict.
    renderDiagram(fill(0.55, 0.4, "It spans about 55% of your frame's width."));
    expect(
      screen.getByText("It spans about 55% of your frame's width."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /M 42 against one Seestar frame/ }),
    ).toBeInTheDocument();
  });

  it("keeps the frame's edge on top of an overflowing object", () => {
    // Painted under a translucent wash the dashed frame reads as a smudge, not
    // as the edge of your field — which is the one thing this picture is for.
    // SVG paints in document order, so the frame must come last.
    const { container } = renderDiagram(fill(1.4, 1.2));
    const shapes = [...container.querySelectorAll("svg > *")].map((n) => n.tagName);
    expect(shapes.indexOf("ellipse")).toBeLessThan(shapes.indexOf("rect"));
  });

  it("draws the object bigger than the frame when it overflows", () => {
    const { container } = renderDiagram(fill(1.4, 0.9));
    const rect = container.querySelector("rect")!;
    const ellipse = container.querySelector("ellipse")!;
    expect(Number(ellipse.getAttribute("rx")) * 2).toBeGreaterThan(
      Number(rect.getAttribute("width")));
    // …and still inside the drawing: the viewBox was widened to hold it.
    const w = Number(container.querySelector("svg")!
      .getAttribute("viewBox")!.split(" ")[2]);
    expect(w).toBeGreaterThan(Number(ellipse.getAttribute("rx")) * 2);
  });
});
