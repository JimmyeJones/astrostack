import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ClosingSeasonNote } from "./ClosingSeasonNote";
import * as client from "../api/client";
import type { ClosingTarget, SeasonClosing } from "../api/client";

function row(over: Partial<ClosingTarget> = {}): ClosingTarget {
  return {
    safe: "m_42", name: "M 42", minutes_now: 180, weeks_left: 0,
    last_night: "2026-03-03", total_exposure_s: 3600, noise_gain: 0.29,
    ...over,
  };
}

function plan(targets: ClosingTarget[]): SeasonClosing {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    generated_utc: "2026-01-20T21:00:00+00:00",
    min_altitude_deg: 30, horizon_weeks: 8, targets,
  };
}

function renderNote() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <ClosingSeasonNote />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("ClosingSeasonNote", () => {
  it("speaks when a target's season ends this week, and points at the planner", async () => {
    vi.spyOn(client.api, "getSeasonClosing").mockResolvedValue(plan([row()]));
    renderNote();
    await screen.findByTestId("closing-season-note");
    expect(screen.getByText(/This is your last week for M 42/)).toBeInTheDocument();
    expect(screen.getByText("See what's leaving")).toHaveAttribute("href", "/tonight");
  });

  it("stays out of the way for a season that is merely ending eventually", async () => {
    // The whole point of the split: the Tonight card lists a target five weeks
    // out, the Dashboard does not. Somebody came here to look at pictures.
    const spy = vi.spyOn(client.api, "getSeasonClosing")
      .mockResolvedValue(plan([row({ weeks_left: 5 })]));
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("closing-season-note")).toBeNull();
  });

  it("renders nothing when nothing is leaving, or on an older backend", async () => {
    const empty = vi.spyOn(client.api, "getSeasonClosing")
      .mockResolvedValue(plan([]));
    const { unmount } = renderNote();
    await waitFor(() => expect(empty).toHaveBeenCalled());
    expect(screen.queryByTestId("closing-season-note")).toBeNull();
    unmount();

    vi.restoreAllMocks();
    const failed = vi.spyOn(client.api, "getSeasonClosing")
      .mockRejectedValue(new Error("404"));
    renderNote();
    await waitFor(() => expect(failed).toHaveBeenCalled());
    expect(screen.queryByTestId("closing-season-note")).toBeNull();
  });
});
