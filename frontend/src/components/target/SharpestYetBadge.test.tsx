import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { StackRun } from "../../api/client";
import { SharpestYetBadge } from "./SharpestYetBadge";

// A minimal StackRun with just the fields the badge reads (the rest are
// irrelevant to the sharpness beat).
const run = (fwhm: number | null, date: string): StackRun =>
  ({
    id: 1,
    timestamp_utc: date,
    output_basename: "x",
    n_frames_used: 20,
    canvas_w: 100,
    canvas_h: 100,
    coverage_min: 1,
    coverage_max: 1,
    has_fits: true,
    has_tiff: false,
    has_preview: true,
    stack_fwhm_px: fwhm,
  }) as unknown as StackRun;

function renderBadge(name: string, runs: StackRun[] | undefined) {
  return render(
    <MantineProvider>
      <SharpestYetBadge name={name} runs={runs} />
    </MantineProvider>,
  );
}

describe("SharpestYetBadge", () => {
  it("celebrates a new sharpest run, naming the target, both values, and the prior date", () => {
    renderBadge("M31", [
      run(2.1, "2026-07-24T22:00:00Z"),
      run(2.6, "2026-07-12T21:00:00Z"),
    ]);
    expect(screen.getByText(/Your sharpest M31 yet/)).toBeInTheDocument();
    expect(screen.getByText(/2\.1 px, beating your 2\.6 px/)).toBeInTheDocument();
  });

  it("renders nothing on the first run", () => {
    renderBadge("M31", [run(2.1, "2026-07-24T22:00:00Z")]);
    expect(screen.queryByText(/sharpest/i)).toBeNull();
  });

  it("renders nothing when the newest run isn't a record", () => {
    renderBadge("M31", [
      run(3.0, "2026-07-24T22:00:00Z"),
      run(2.4, "2026-07-12T21:00:00Z"),
    ]);
    expect(screen.queryByText(/sharpest/i)).toBeNull();
  });

  it("renders nothing when runs are missing", () => {
    renderBadge("M31", undefined);
    expect(screen.queryByText(/sharpest/i)).toBeNull();
  });
});
