import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { MemoryRouter } from "react-router-dom";

import { RejectionBreakdown } from "./RejectionBreakdown";
import type { RejectionBucket, RejectionSummary } from "../../api/client";

function renderBreakdown(summary: RejectionSummary, onRunPlateSolve?: () => void) {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <RejectionBreakdown summary={summary} onRunPlateSolve={onRunPlateSolve} />
      </MemoryRouter>
    </MantineProvider>,
  );
}

function bucket(key: string, over: Partial<RejectionBucket> = {}): RejectionBucket {
  return { key, label: `Label ${key}`, count: 5, note: `Note ${key}`, ...over };
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

describe("RejectionBreakdown advice you can act on", () => {
  it("links the timed-out bucket to the setting its note names", () => {
    renderBreakdown({ ...SUMMARY, buckets: [bucket("solve_timeout")] });
    expect(screen.getByText("Open plate-solving settings →"))
      .toHaveAttribute("href", "/settings/plate-solving");
  });

  it("runs Plate Solve from the bucket that tells you to", () => {
    const run = vi.fn();
    renderBreakdown({ ...SUMMARY, buckets: [bucket("unsolved")] }, run);
    fireEvent.click(screen.getByRole("button", { name: "Run Plate Solve" }));
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("offers no Plate Solve button on a surface that has no such action", () => {
    renderBreakdown({ ...SUMMARY, buckets: [bucket("unsolved")] });
    expect(screen.queryByRole("button", { name: "Run Plate Solve" })).toBeNull();
  });

  it("acts on the headline verdict too, keyed rather than matched on its wording", () => {
    renderBreakdown({
      ...SUMMARY,
      verdict: { tone: "warn", key: "solve_timeout", text: "Most of your subs ran out of time…" },
      buckets: [bucket("clouds")],
    });
    expect(screen.getByText("Open plate-solving settings →"))
      .toHaveAttribute("href", "/settings/plate-solving");
  });

  it("resolves a dominant-bucket verdict through the same map as the bucket", () => {
    renderBreakdown({
      ...SUMMARY,
      verdict: { tone: "warn", key: "dominant:unsolved", text: "Mostly subs not located yet…" },
      buckets: [bucket("clouds")],
    }, vi.fn());
    expect(screen.getByRole("button", { name: "Run Plate Solve" })).toBeInTheDocument();
  });

  it("offers one control, not two, when the verdict is about a bucket below it", () => {
    renderBreakdown({
      ...SUMMARY,
      verdict: { tone: "warn", key: "dominant:solve_timeout", text: "Mostly timed out…" },
      buckets: [bucket("solve_timeout"), bucket("clouds")],
    });
    expect(screen.getAllByText("Open plate-solving settings →")).toHaveLength(1);
  });

  it("offers nothing on advice with no destination, or against an older backend", () => {
    renderBreakdown(SUMMARY, vi.fn());  // trailed + clouds, verdict with no key
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
