import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";

import { FrameCountBadge } from "./FrameCountBadge";

function renderBadge(nFramesUsed: number, color?: string) {
  return render(
    <MantineProvider>
      <FrameCountBadge nFramesUsed={nFramesUsed} color={color} />
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
});
