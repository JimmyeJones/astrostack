import { MantineProvider } from "@mantine/core";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { VideoSharpnessProfile } from "../api/client";
import {
  VideoSharpnessCard, optionLine, sharpnessCurvePoints,
} from "./VideoSharpnessCard";

function profile(over: Partial<VideoSharpnessProfile> = {}): VideoSharpnessProfile {
  return {
    curve: [1, 0.9, 0.6, 0.3, 0.2, 0.2],
    cut_fraction: 0.3,
    options: [
      { percent: 15, n_frames: 30, sharpness_vs_typical: 2.4, noise_gain: 5.5 },
      { percent: 30, n_frames: 60, sharpness_vs_typical: 1.6, noise_gain: 7.7 },
      { percent: 50, n_frames: 100, sharpness_vs_typical: 1.2, noise_gain: 10 },
    ],
    suggested_percent: 15,
    spread: "variable",
    summary: "The seeing jumped around a lot, so being pickier pays: keeping 15% …",
    ...over,
  };
}

function renderCard(p: VideoSharpnessProfile | null, onUse?: (n: number) => void) {
  return render(
    <MantineProvider>
      <VideoSharpnessCard profile={p} onUseSuggestion={onUse} />
    </MantineProvider>,
  );
}

describe("sharpnessCurvePoints", () => {
  it("plots on a fixed 0..1 axis so a steady capture looks flat", () => {
    // The whole point of not reusing `Sparkline`: min/max autoscaling would draw
    // these near-identical scores as a dramatic cliff and mislead the beginner.
    const pts = sharpnessCurvePoints([1, 0.999, 0.998], 100, 50);
    const ys = pts.map((p) => p.y);
    expect(Math.max(...ys) - Math.min(...ys)).toBeLessThan(1);
  });

  it("puts 1.0 at the top and 0 at the bottom", () => {
    const [top, bottom] = sharpnessCurvePoints([1, 0], 100, 50, 0);
    expect(top.y).toBe(0);
    expect(bottom.y).toBe(50);
  });

  it("clamps out-of-range values instead of drawing outside the box", () => {
    const pts = sharpnessCurvePoints([2, -1], 100, 50, 0);
    expect(pts[0].y).toBe(0);
    expect(pts[1].y).toBe(50);
  });

  it("returns nothing for an empty curve", () => {
    expect(sharpnessCurvePoints([], 100, 50)).toEqual([]);
  });
});

describe("optionLine", () => {
  it("states the trade-off in both directions", () => {
    expect(optionLine({
      percent: 15, n_frames: 30, sharpness_vs_typical: 2.4, noise_gain: 5.5,
    })).toBe("15% · 30 frames · 2.4× sharper · 6× cleaner");
  });
});

describe("VideoSharpnessCard", () => {
  it("shows the verdict, the summary and every setting's numbers", () => {
    renderCard(profile());
    expect(screen.getByText("How steady was your capture?")).toBeInTheDocument();
    expect(screen.getByText("Jumpy seeing")).toBeInTheDocument();
    expect(screen.getByText(/being pickier pays/)).toBeInTheDocument();
    expect(screen.getByText(/^15% · 30 frames/)).toBeInTheDocument();
    expect(screen.getByText(/^50% · 100 frames/)).toBeInTheDocument();
  });

  it("hands the suggested setting back when the button is pressed", () => {
    const onUse = vi.fn();
    renderCard(profile({ suggested_percent: 50 }), onUse);
    fireEvent.click(screen.getByRole("button", { name: /Try 50% instead/ }));
    expect(onUse).toHaveBeenCalledWith(50);
  });

  it("does not nag when the setting used was already the right one", () => {
    renderCard(profile({
      summary: "The air was steady … Keeping 50% used 100 frames … a good choice here.",
      suggested_percent: 50,
    }), vi.fn());
    expect(screen.queryByRole("button", { name: /instead/ })).toBeNull();
  });

  it("renders nothing for a result stacked before the scores were kept", () => {
    renderCard(null);
    expect(screen.queryByText("How steady was your capture?")).toBeNull();
  });

  it("renders nothing for an empty curve", () => {
    renderCard(profile({ curve: [] }));
    expect(screen.queryByText("How steady was your capture?")).toBeNull();
  });

  it("omits the cut marker when nothing has been stacked yet", () => {
    const { container } = renderCard(profile({ cut_fraction: 0 }));
    expect(container.querySelector("svg line")).toBeNull();
    expect(screen.queryByText(/dashed line/)).toBeNull();
  });
});
