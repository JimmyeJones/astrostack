import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CurvesWidget } from "./CurvesWidget";
import type { Pt } from "./curveDrag";

/** Render the widget with a controlled point list and capture onChange calls. */
function setup(initial: Pt[]) {
  const onChange = vi.fn();
  render(<MantineProvider><CurvesWidget points={initial} onChange={onChange} /></MantineProvider>);
  return { onChange };
}

describe("CurvesWidget keyboard access (a11y)", () => {
  it("exposes each point as a focusable slider", () => {
    setup([[0, 0], [0.5, 0.5], [1, 1]]);
    const handles = screen.getAllByRole("slider");
    expect(handles).toHaveLength(3);
    handles.forEach((h) => expect(h).toHaveAttribute("tabindex", "0"));
    expect(handles[1]).toHaveAttribute("aria-label", "Curve point 2 of 3");
    expect(handles[0].getAttribute("aria-label")).toContain("endpoint");
  });

  it("nudges an interior point up with ArrowUp", () => {
    const { onChange } = setup([[0, 0], [0.5, 0.5], [1, 1]]);
    fireEvent.keyDown(screen.getAllByRole("slider")[1], { key: "ArrowUp" });
    expect(onChange).toHaveBeenCalledWith([[0, 0], [0.5, 0.52], [1, 1]]);
  });

  it("uses a coarser step with Shift", () => {
    const { onChange } = setup([[0, 0], [0.5, 0.5], [1, 1]]);
    fireEvent.keyDown(screen.getAllByRole("slider")[1], { key: "ArrowRight", shiftKey: true });
    const moved = onChange.mock.calls[0][0] as Pt[];
    expect(moved[1][0]).toBeCloseTo(0.6, 6);
  });

  it("removes an interior point with Delete", () => {
    const { onChange } = setup([[0, 0], [0.5, 0.5], [1, 1]]);
    fireEvent.keyDown(screen.getAllByRole("slider")[1], { key: "Delete" });
    expect(onChange).toHaveBeenCalledWith([[0, 0], [1, 1]]);
  });

  it("keeps an endpoint's x locked when nudged horizontally", () => {
    const { onChange } = setup([[0, 0], [1, 1]]);
    fireEvent.keyDown(screen.getAllByRole("slider")[0], { key: "ArrowRight" });
    // x stays 0; only y could change (ArrowRight adds to x, which is locked → no move).
    expect(onChange).toHaveBeenCalledWith([[0, 0], [1, 1]]);
  });

  it("adds a point via the keyboard-accessible 'add point' button", () => {
    const { onChange } = setup([[0, 0], [1, 1]]);
    fireEvent.click(screen.getByRole("button", { name: /add point/i }));
    expect(onChange).toHaveBeenCalledWith([[0, 0], [0.5, 0.5], [1, 1]]);
  });
});
