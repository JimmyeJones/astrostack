import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";

import { RejectionBreakdown } from "./RejectionBreakdown";
import type { RejectionSummary } from "../../api/client";

function renderBreakdown(summary: RejectionSummary) {
  return render(
    <MantineProvider>
      <RejectionBreakdown summary={summary} />
    </MantineProvider>,
  );
}

const SUMMARY: RejectionSummary = {
  used: 412,
  dropped: 88,
  dropped_fraction: 0.176,
  verdict: { tone: "ok", text: "A few frames didn't make the cut — still a solid stack." },
  buckets: [
    {
      key: "trailed",
      label: "Trailed frames (satellites or planes)",
      count: 60,
      note: "A plane or satellite crossed these — leaving them out keeps streaks out of your picture.",
    },
    {
      key: "clouds",
      label: "Cloud, haze or moonlight",
      count: 28,
      note: "Fewer stars or a brighter sky than usual — cloud, haze or moonlight got in the way.",
    },
  ],
};

describe("RejectionBreakdown", () => {
  it("shows the headline verdict and used/total sentence", () => {
    renderBreakdown(SUMMARY);
    expect(
      screen.getByText("A few frames didn't make the cut — still a solid stack."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("412 of 500 frames went into your picture."),
    ).toBeInTheDocument();
  });

  it("lists each bucket with its label, count and plain-language note", () => {
    renderBreakdown(SUMMARY);
    expect(screen.getByText("Trailed frames (satellites or planes)")).toBeInTheDocument();
    expect(screen.getByText("60")).toBeInTheDocument();
    expect(screen.getByText("Cloud, haze or moonlight")).toBeInTheDocument();
    expect(screen.getByText("28")).toBeInTheDocument();
    expect(
      screen.getByText(/A plane or satellite crossed these/),
    ).toBeInTheDocument();
  });
});
