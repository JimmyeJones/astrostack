import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BestMonthsStrip } from "./BestMonthsStrip";
import type { BestMonths, MonthObservability } from "../api/client";
import * as client from "../api/client";

function rows(usable: number[]): MonthObservability[] {
  return usable.map((u, i) => ({
    month: i + 1,
    usable_dark_minutes: u,
    max_transit_alt_deg: u > 0 ? 45 : 5,
    dark_minutes: 400,
  }));
}

function payload(over: Partial<BestMonths> = {}): BestMonths {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    target_has_position: true,
    min_altitude_deg: 30,
    year: 2026,
    months: rows([290, 190, 40, 0, 0, 0, 0, 0, 0, 0, 290, 320]),
    ...over,
  };
}

function renderStrip(safe = "M_42") {
  return render(
    <MantineProvider>
      <QueryClientProvider client={new QueryClient()}>
        <BestMonthsStrip safe={safe} />
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("BestMonthsStrip", () => {
  it("shows the seasonal verdict and a 12-cell strip for a placed target", async () => {
    vi.spyOn(client.api, "bestMonths").mockResolvedValue(payload());
    renderStrip();
    await waitFor(() =>
      expect(screen.getByText("Best time of year to shoot this")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Best around Nov–Mar/)).toBeInTheDocument();
    expect(screen.getByText(/highest in Dec/)).toBeInTheDocument();
    // One heat cell per month, each with an accessible label.
    expect(screen.getByLabelText(/Dec: up ~5\.3 h in the dark/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Jun: doesn't clear the floor/)).toBeInTheDocument();
  });

  it("self-hides when the planner returns no months (no location/position)", async () => {
    vi.spyOn(client.api, "bestMonths").mockResolvedValue(
      payload({ location_source: "none", observer: null, target_has_position: true, months: [] }),
    );
    const { container } = renderStrip();
    await waitFor(() => expect(client.api.bestMonths).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
