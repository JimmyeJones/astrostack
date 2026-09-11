import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";

import { FrameCountBadge } from "./FrameCountBadge";

function renderBadge(
  nFramesUsed: number, color?: string, fieldFulls?: number | null,
) {
  return render(
    <MantineProvider>
      <FrameCountBadge
        nFramesUsed={nFramesUsed}
        fieldFulls={fieldFulls}
        color={color}
      />
    </MantineProvider>,
  );
}

describe("FrameCountBadge", () => {
  it("shows a plain frame count for a healthy stack with no warning tooltip", () => {
    renderBadge(30);
    expect(screen.getByText("30 frames")).toBeInTheDocument();
    // No thin-stack cue: the warning icon (rendered as an svg with a title-less
    // alert-triangle) and its tooltip aria are absent.
    expect(document.querySelector(".tabler-icon-alert-triangle")).toBeNull();
  });

  it("carries the honest thin-stack cue on a single-frame 'stack'", () => {
    renderBadge(1);
    // Count is still shown…
    expect(screen.getByText("1 frames")).toBeInTheDocument();
    // …plus the warning-triangle icon marking it as not a real stack.
    expect(document.querySelector(".tabler-icon-alert-triangle")).not.toBeNull();
  });

  it("flags a very thin (2–4 frame) stack too", () => {
    renderBadge(3);
    expect(screen.getByText("3 frames")).toBeInTheDocument();
    expect(document.querySelector(".tabler-icon-alert-triangle")).not.toBeNull();
  });

  it("does not warn right above the threshold", () => {
    renderBadge(5);
    expect(screen.getByText("5 frames")).toBeInTheDocument();
    expect(document.querySelector(".tabler-icon-alert-triangle")).toBeNull();
  });

  it("flags a mosaic that is only one sub deep, though its count is nine", () => {
    // Nine subs over a 3x3 raster: the picture is a single sub everywhere, which
    // is exactly the speckle this cue exists for — and the count alone (9 > 4)
    // says nothing. The Target page has read it this way since v0.419.1.
    renderBadge(9, undefined, 9);
    // The count is still the count — the badge never misreports what combined.
    expect(screen.getByText("9 frames")).toBeInTheDocument();
    expect(document.querySelector(".tabler-icon-alert-triangle")).not.toBeNull();
  });

  it("leaves a genuinely deep mosaic alone", () => {
    // 180 subs over the same 3x3 is 20 a panel — deep, and must not be nagged.
    renderBadge(180, undefined, 9);
    expect(screen.getByText("180 frames")).toBeInTheDocument();
    expect(document.querySelector(".tabler-icon-alert-triangle")).toBeNull();
  });

  it("reads the count itself on a single field and on an older backend", () => {
    // field_fulls 1.0 (single field) and a missing field must both behave
    // exactly as the badge always has — no scaling, no new wording.
    renderBadge(9, undefined, 1);
    expect(document.querySelector(".tabler-icon-alert-triangle")).toBeNull();
    renderBadge(9, undefined, null);
    expect(document.querySelector(".tabler-icon-alert-triangle")).toBeNull();
  });
});
