import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CombineView } from "./Combine";
import * as client from "../api/client";
import type { StackRun, Target } from "../api/client";

function mkTarget(name: string): Target {
  return {
    safe_name: name, name, ra_deg: null, dec_deg: null, n_frames: 5,
    n_frames_accepted: 5, total_exposure_s: 0, last_activity_utc: null,
    has_preview: false, notes: null, tags: [],
  };
}

function mkRun(id: number): StackRun {
  return {
    id, timestamp_utc: "2026-01-01", output_basename: `stack_${id}`,
    n_frames_used: 10, canvas_w: 480, canvas_h: 320, coverage_min: 1,
    coverage_max: 10, has_fits: true, has_tiff: true, has_preview: true, notes: null,
  };
}

function renderView() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><CombineView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("CombineView", () => {
  it("renders channel slots and disables combine until assigned", async () => {
    vi.spyOn(client.api, "listTargets").mockResolvedValue([mkTarget("M_42")]);
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([mkRun(1)]);
    renderView();

    await waitFor(() => expect(screen.getByText("Luminance (L)")).toBeInTheDocument());
    expect(screen.getByText("Red (R)")).toBeInTheDocument();
    // Combine button disabled with nothing assigned.
    const btn = screen.getByRole("button", { name: /Combine/ });
    expect(btn).toBeDisabled();
  });
});
