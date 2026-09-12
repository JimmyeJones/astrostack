import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ClosingSeasonCard } from "./ClosingSeasonCard";
import * as client from "../../api/client";
import type { ClosingTarget, SeasonClosing } from "../../api/client";

function row(over: Partial<ClosingTarget> = {}): ClosingTarget {
  return {
    safe: "m_42", name: "M 42", minutes_now: 180, weeks_left: 3,
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

function renderCard() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <ClosingSeasonCard />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("ClosingSeasonCard", () => {
  it("names the targets that are leaving, and links to each", async () => {
    vi.spyOn(client.api, "getSeasonClosing").mockResolvedValue(plan([
      row({ safe: "m_31", name: "M 31", weeks_left: 1, total_exposure_s: 1200 }),
      row(),
    ]));
    renderCard();

    await screen.findByTestId("closing-season");
    expect(screen.getByText(/2 of your targets/)).toBeInTheDocument();
    expect(screen.getByText("M 31")).toHaveAttribute("href", "/targets/m_31");
    expect(screen.getByText("M 42")).toHaveAttribute("href", "/targets/m_42");
    // The consequence, not the mechanism — this is why it is worth a clear night.
    expect(screen.getByText(/gone until the same season next year/))
      .toBeInTheDocument();
    // The week or less case is the one that earns a badge.
    expect(screen.getAllByText("Last chance")).toHaveLength(1);
  });

  it("renders nothing at all when nothing is leaving", async () => {
    // Most of the year. A planning card that speaks anyway is exactly the
    // always-on banner the owner's standing complaint is about.
    const spy = vi.spyOn(client.api, "getSeasonClosing")
      .mockResolvedValue(plan([]));
    renderCard();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("closing-season")).toBeNull();
  });

  it("stays silent on an older backend or a failed fetch", async () => {
    const spy = vi.spyOn(client.api, "getSeasonClosing")
      .mockRejectedValue(new Error("404"));
    renderCard();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("closing-season")).toBeNull();
  });

  it("does not badge a target that still has a few weeks", async () => {
    vi.spyOn(client.api, "getSeasonClosing")
      .mockResolvedValue(plan([row({ weeks_left: 4 })]));
    renderCard();
    await screen.findByTestId("closing-season");
    expect(screen.queryByText("Last chance")).toBeNull();
    // Headline and detail line both carry it — the point is that the countdown
    // reaches the reader, not which element it lands in.
    expect(screen.getAllByText(/about 4 weeks left/).length).toBeGreaterThan(0);
  });
});
