import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { MemoryRouter } from "react-router-dom";

import { RejectionBreakdown } from "./RejectionBreakdown";
import type { RejectionBucket, RejectionSummary } from "../../api/client";

function renderBreakdown(
  summary: RejectionSummary,
  onRunPlateSolve?: () => void,
  opts: { onTryHarder?: () => void; deepRescueOffered?: boolean } = {},
) {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <RejectionBreakdown summary={summary} onRunPlateSolve={onRunPlateSolve}
          onTryHarder={opts.onTryHarder}
          deepRescueOffered={opts.deepRescueOffered} />
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

describe("RejectionBreakdown — trying harder on a faint field", () => {
  it("offers the deep-image rescue instead of Plate Solve once the server says it would work", () => {
    // These subs have already been offered to the plate solver and beaten it, so
    // running it again would spend the same minutes for the same answer. One
    // control, and it is the one that can actually change the outcome.
    const tryHarder = vi.fn();
    renderBreakdown({ ...SUMMARY, buckets: [bucket("unsolved")] }, vi.fn(), {
      onTryHarder: tryHarder, deepRescueOffered: true,
    });
    expect(screen.queryByRole("button", { name: "Run Plate Solve" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try harder to locate these" }));
    expect(tryHarder).toHaveBeenCalledTimes(1);
  });

  it("keeps Plate Solve where the rescue would do nothing", () => {
    const run = vi.fn();
    const tryHarder = vi.fn();
    renderBreakdown({ ...SUMMARY, buckets: [bucket("unsolved")] }, run, {
      onTryHarder: tryHarder, deepRescueOffered: false,
    });
    expect(screen.queryByRole("button", { name: "Try harder to locate these" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Run Plate Solve" }));
    expect(run).toHaveBeenCalledTimes(1);
    expect(tryHarder).not.toHaveBeenCalled();
  });

  it("says nothing against an older backend that omits the flag", () => {
    // `deepRescueOffered` left undefined is exactly what an older backend's
    // response reads as — the page must behave as it always did.
    renderBreakdown({ ...SUMMARY, buckets: [bucket("unsolved")] }, vi.fn(), {
      onTryHarder: vi.fn(),
    });
    expect(screen.getByRole("button", { name: "Run Plate Solve" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try harder to locate these" })).toBeNull();
  });

  it("offers no rescue button on a surface that has no such action", () => {
    renderBreakdown({ ...SUMMARY, buckets: [bucket("unsolved")] }, undefined, {
      deepRescueOffered: true,
    });
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("resolves a dominant-unsolved verdict to the rescue too, through the same map", () => {
    const tryHarder = vi.fn();
    renderBreakdown({
      ...SUMMARY,
      verdict: { tone: "warn", key: "dominant:unsolved", text: "Mostly subs not located yet…" },
      buckets: [bucket("clouds")],
    }, vi.fn(), { onTryHarder: tryHarder, deepRescueOffered: true });
    fireEvent.click(screen.getByRole("button", { name: "Try harder to locate these" }));
    expect(tryHarder).toHaveBeenCalledTimes(1);
  });

  it("offers one control, not two, when the verdict is about the unsolved bucket below it", () => {
    renderBreakdown({
      ...SUMMARY,
      verdict: { tone: "warn", key: "dominant:unsolved", text: "Mostly subs not located yet…" },
      buckets: [bucket("unsolved"), bucket("clouds")],
    }, vi.fn(), { onTryHarder: vi.fn(), deepRescueOffered: true });
    expect(screen.getAllByRole("button", { name: "Try harder to locate these" }))
      .toHaveLength(1);
  });
});
