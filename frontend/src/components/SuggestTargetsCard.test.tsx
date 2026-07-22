import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SuggestTargetsCard } from "./SuggestTargetsCard";
import type { SuggestResponse, SuggestedTarget } from "../api/client";
import * as client from "../api/client";

function suggestion(over: Partial<SuggestedTarget> = {}): SuggestedTarget {
  return {
    id: "M27",
    name: "Dumbbell Nebula",
    ra_deg: 299.9,
    dec_deg: 22.7,
    type: "planetary nebula",
    con: "Vul",
    blurb: "A bright planetary nebula in Vulpecula.",
    max_altitude_deg: 64,
    transit_utc: "2026-07-22T23:00:00+00:00",
    minutes_above_min_alt: 420,
    moon_separation_deg: 80,
    moon_up_fraction: 0.0,
    usable_start_utc: "2026-07-22T22:00:00+00:00",
    usable_end_utc: "2026-07-23T05:00:00+00:00",
    score: 88,
    size_arcmin: 8,
    framing: { level: "fits", text: "fits comfortably in one frame" },
    ...over,
  };
}

function response(over: Partial<SuggestResponse> = {}): SuggestResponse {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    min_altitude_deg: 30,
    suggestions: [suggestion()],
    ...over,
  };
}

function renderCard() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <SuggestTargetsCard />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("SuggestTargetsCard", () => {
  it("shows a suggested showpiece with its blurb and observability line", async () => {
    vi.spyOn(client.api, "suggestTargets").mockResolvedValue(response());
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Try something new tonight")).toBeInTheDocument(),
    );
    expect(screen.getByText("M27 · Dumbbell Nebula")).toBeInTheDocument();
    expect(screen.getByText("A bright planetary nebula in Vulpecula.")).toBeInTheDocument();
    expect(screen.getByText(/Climbs to 64°, up about 7 h tonight/)).toBeInTheDocument();
  });

  it("offers a per-target 'Add to calendar' .ics download (id encoded)", async () => {
    vi.spyOn(client.api, "suggestTargets").mockResolvedValue(
      response({ suggestions: [suggestion({ id: "NGC 7000", name: "North America Nebula" })] }),
    );
    renderCard();
    const link = await screen.findByRole("link", { name: /Add to calendar/ });
    expect(link).toHaveAttribute("href", "/api/plan/suggest/NGC%207000/calendar.ics");
    expect(link).toHaveAttribute("download");
  });

  it("self-hides when there's nothing new to suggest", async () => {
    vi.spyOn(client.api, "suggestTargets").mockResolvedValue(
      response({ location_source: "none", observer: null, suggestions: [] }),
    );
    const { container } = renderCard();
    await waitFor(() => expect(client.api.suggestTargets).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });
});
