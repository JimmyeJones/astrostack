import { describe, it, expect } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MantineProvider } from "@mantine/core";
import { NoiseReadout, CleanestBadge, cleanestRunId, hasNoise } from "./NoiseBadge";
import type { StackRun } from "../api/client";

function wrap(node: React.ReactNode) {
  return render(<MantineProvider>{node}</MantineProvider>);
}

function run(id: number, noise_sigma?: number | null): StackRun {
  return {
    id,
    timestamp_utc: "2026-01-01T00:00:00",
    output_basename: `run${id}`,
    n_frames_used: 10,
    canvas_w: 100,
    canvas_h: 100,
    coverage_min: 0,
    coverage_max: 10,
    has_fits: true,
    has_tiff: true,
    has_preview: true,
    notes: null,
    noise_sigma,
  };
}

describe("NoiseBadge", () => {
  it("NoiseReadout shows the σ to 3 decimals when present", () => {
    wrap(<NoiseReadout sigma={0.0213} />);
    expect(screen.getByText("Noise 0.021")).toBeInTheDocument();
  });

  it("NoiseReadout renders nothing when σ is absent", () => {
    wrap(<NoiseReadout sigma={null} />);
    expect(screen.queryByText(/Noise/)).not.toBeInTheDocument();
    cleanup();
    wrap(<NoiseReadout sigma={undefined} />);
    expect(screen.queryByText(/Noise/)).not.toBeInTheDocument();
  });

  it("CleanestBadge renders only when isCleanest", () => {
    wrap(<CleanestBadge isCleanest />);
    expect(screen.getByText("Cleanest")).toBeInTheDocument();
    cleanup();
    wrap(<CleanestBadge isCleanest={false} />);
    expect(screen.queryByText("Cleanest")).not.toBeInTheDocument();
  });

  it("hasNoise guards missing/negative values", () => {
    expect(hasNoise(0)).toBe(true);
    expect(hasNoise(0.02)).toBe(true);
    expect(hasNoise(-1)).toBe(false);
    expect(hasNoise(null)).toBe(false);
    expect(hasNoise(undefined)).toBe(false);
  });

  it("cleanestRunId picks the lowest-σ run, needs at least two measured", () => {
    expect(cleanestRunId([run(1, 0.05), run(2, 0.02), run(3, 0.08)])).toBe(2);
    // Only one measured → no comparison, so no cleanest badge.
    expect(cleanestRunId([run(1, 0.02), run(2, null)])).toBeNull();
    expect(cleanestRunId([run(1, null), run(2, null)])).toBeNull();
    expect(cleanestRunId([])).toBeNull();
  });
});
