import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SkylineEditor } from "./SkylineEditor";
import {
  SKYLINE_BUCKETS, SKYLINE_MAX_ALT, STRIP, altitudeAtAz, groundPolygonPoints, nearestBucket,
  profileToHeights, xAtAz, yAtAlt, type HorizonPoint,
} from "../skyline";

function renderEditor(value: HorizonPoint[] = []) {
  const onChange = vi.fn();
  render(
    <MantineProvider>
      <SkylineEditor value={value} onChange={onChange} />
    </MantineProvider>,
  );
  return onChange;
}

/** jsdom gives every element a zero-sized box, so the strip can't map a pointer
 *  to a bearing without one. Pin it to the viewBox 1:1 — then a click at
 *  (xAtAz(az), yAtAlt(alt)) means exactly that bearing and altitude. */
function withStripBox() {
  const strip = screen.getByTestId("skyline-strip");
  vi.spyOn(strip, "getBoundingClientRect").mockReturnValue({
    left: 0, top: 0, width: STRIP.w, height: STRIP.h,
    right: STRIP.w, bottom: STRIP.h, x: 0, y: 0, toJSON: () => ({}),
  } as DOMRect);
  return strip;
}

/** jsdom implements no `PointerEvent`, so `fireEvent.pointerDown` silently
 *  drops `clientX`/`clientY` — a drag test written with it passes while
 *  measuring nothing. A `MouseEvent` of the same type carries the coordinates
 *  and reaches React's pointer handler, which is all this component reads. */
function pointer(el: Element, type: string, clientX: number, clientY: number) {
  fireEvent(el, new MouseEvent(type, {
    bubbles: true, cancelable: true, clientX, clientY,
  }));
}

describe("SkylineEditor", () => {
  it("starts flat and says so in plain language", () => {
    renderEditor([]);
    expect(screen.getByTestId("skyline-summary").textContent)
      .toMatch(/open horizon/i);
    expect(screen.getByTestId("skyline-ground")).toHaveAttribute(
      "points", groundPolygonPoints(profileToHeights([])));
  });

  it("draws a saved profile back, so what you typed is what you see", () => {
    const profile: HorizonPoint[] = [[0, 0], [180, 40]];
    renderEditor(profile);
    expect(screen.getByTestId("skyline-ground")).toHaveAttribute(
      "points", groundPolygonPoints(profileToHeights(profile)));
    expect(screen.getByTestId("skyline-summary").textContent).toContain("40°");
  });

  it("a drag saves a profile the planner reads back as the drawn skyline", () => {
    const onChange = renderEditor([]);
    const strip = withStripBox();

    // Sweep from due east to due south at 25°.
    pointer(strip, "pointerdown", xAtAz(90), yAtAlt(25));
    pointer(strip, "pointermove", xAtAz(180), yAtAlt(25));
    pointer(strip, "pointerup", xAtAz(180), yAtAlt(25));

    expect(onChange).toHaveBeenCalled();
    const saved: HorizonPoint[] = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    // The shape the backend validator accepts: whole-degree pairs, in range.
    expect(saved).toHaveLength(SKYLINE_BUCKETS);
    expect(saved.every(([az, alt]) =>
      Number.isInteger(az) && Number.isInteger(alt)
      && az >= 0 && az < 360 && alt >= 0 && alt <= 90)).toBe(true);
    // …and it means what was drawn: blocked across the east-to-south arc, open
    // elsewhere, read through the same interpolation the planner uses.
    expect(altitudeAtAz(saved, 90)).toBeCloseTo(25);
    expect(altitudeAtAz(saved, 135)).toBeCloseTo(25);
    expect(altitudeAtAz(saved, 180)).toBeCloseTo(25);
    expect(altitudeAtAz(saved, 315)).toBeCloseTo(0);
  });

  it("shows the drag as it happens, before it is committed", () => {
    const onChange = renderEditor([]);
    const strip = withStripBox();
    pointer(strip, "pointerdown", xAtAz(45), yAtAlt(30));

    const drawn = screen.getByTestId("skyline-ground").getAttribute("points");
    expect(drawn).not.toBe(groundPolygonPoints(profileToHeights([])));
    // Nothing is saved until the gesture ends.
    expect(onChange).not.toHaveBeenCalled();

    pointer(strip, "pointerup", xAtAz(45), yAtAlt(30));
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("a preset is one click and lands on the right side of the sky", () => {
    const onChange = renderEditor([]);
    fireEvent.click(screen.getByText("Trees to the north"));
    const saved: HorizonPoint[] = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(saved[nearestBucket(0)][1]).toBeGreaterThan(saved[nearestBucket(180)][1]);
  });

  it("'Open sky' and 'Flatten it' both restore the empty profile", () => {
    const onChange = renderEditor([[0, 20], [180, 20]]);
    fireEvent.click(screen.getByText("Open sky"));
    expect(onChange).toHaveBeenLastCalledWith([]);

    fireEvent.click(screen.getByText("Flatten it"));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("offers no 'Flatten it' when there is nothing to flatten", () => {
    renderEditor([]);
    expect(screen.queryByText("Flatten it")).not.toBeInTheDocument();
  });

  it("a drag off the top of the strip can't emit an impossible altitude", () => {
    const onChange = renderEditor([]);
    const strip = withStripBox();
    pointer(strip, "pointerdown", xAtAz(180), -500);
    pointer(strip, "pointerup", xAtAz(180), -500);
    const saved: HorizonPoint[] = onChange.mock.calls[onChange.mock.calls.length - 1][0];
    expect(saved).toHaveLength(SKYLINE_BUCKETS);
    expect(saved.every(([, alt]) => alt >= 0 && alt <= 90)).toBe(true);
    // Pinned at the top of the strip rather than run off it.
    expect(saved[nearestBucket(180)][1]).toBe(SKYLINE_MAX_ALT);
  });
});
