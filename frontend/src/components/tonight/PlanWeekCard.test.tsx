import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlanWeekCard } from "./PlanWeekCard";
import * as client from "../../api/client";
import type { PlanWeek, WeekNight } from "../../api/client";

// Frozen so the "Tonight / Tomorrow / Saturday" labels are deterministic.
const NOW = new Date("2026-09-02T20:00:00");

function night(date: string, over: Partial<WeekNight> = {}): WeekNight {
  return {
    date,
    dark_start_utc: `${date}T20:30:00+00:00`,
    dark_end_utc: `${date}T04:30:00+00:00`,
    dark_minutes: 480,
    moon_illumination: 0.1,
    n_usable: 1,
    best: {
      safe: "M_31", name: "M 31",
      usable_start_utc: `${date}T21:00:00+00:00`,
      usable_end_utc: `${date}T23:30:00+00:00`,
      minutes_above_min_alt: 150,
      max_altitude_deg: 61.2,
      moon_up_fraction: 0,
      score: 60,
    },
    ...over,
  };
}

function plan(over: Partial<PlanWeek> = {}): PlanWeek {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    generated_utc: "2026-09-02T20:00:00+00:00",
    min_altitude_deg: 30,
    horizon_active: false,
    nights_scanned: 7,
    nights: [],
    targets: [],
    n_targets_considered: 1,
    n_targets_with_position: 1,
    ...over,
  };
}

function renderCard(props: { minAlt?: number } = {}) {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <PlanWeekCard {...props} />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

beforeEach(() => vi.setSystemTime(NOW));
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("PlanWeekCard", () => {
  it("says which night to go out on and what to point at", async () => {
    vi.spyOn(client.api, "getPlanWeek").mockResolvedValue(plan({
      nights: [
        night("2026-09-02", { best: { ...night("2026-09-02").best!, score: 30 } }),
        night("2026-09-05", { best: { ...night("2026-09-05").best!, score: 90 } }),
      ],
      targets: [
        { safe: "M_31", name: "M 31", date: "2026-09-05", minutes_above_min_alt: 150, score: 90 },
        { safe: "M_42", name: "M 42", date: "2026-09-06", minutes_above_min_alt: 120, score: 55 },
      ],
    }));
    renderCard();

    await waitFor(() =>
      expect(screen.getByTestId("plan-week")).toBeInTheDocument());
    expect(screen.getByText(/Your best night is Saturday — M 31/)).toBeInTheDocument();
    // Every placed night is a row, named the way a person would name it.
    expect(screen.getByText("Tonight")).toBeInTheDocument();
    expect(screen.getByText("Saturday")).toBeInTheDocument();
    // The target links through to its page rather than being dead text.
    const link = screen.getAllByRole("link", { name: "M 31" })[0];
    expect(link).toHaveAttribute("href", "/targets/M_31");
    // The follow-up line adds the *other* target, not a repeat of the headline.
    expect(screen.getByText(/M 42 — Sunday/)).toBeInTheDocument();
    expect(screen.queryByText(/M 31 — Saturday/)).not.toBeInTheDocument();
  });

  it("explains an empty week instead of showing a blank table", async () => {
    vi.spyOn(client.api, "getPlanWeek").mockResolvedValue(plan({
      location_source: "none", observer: null,
      n_targets_considered: 0, n_targets_with_position: 0,
    }));
    renderCard();

    await waitFor(() =>
      expect(screen.getByTestId("plan-week")).toBeInTheDocument());
    expect(screen.getByText(/Set your observing location/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("flags a night the Moon will spoil, and stays quiet when it won't", async () => {
    vi.spyOn(client.api, "getPlanWeek").mockResolvedValue(plan({
      nights: [
        night("2026-09-03", {
          moon_illumination: 0.92,
          best: { ...night("2026-09-03").best!, moon_up_fraction: 1.0 },
        }),
        // A full Moon that never rises is not a problem — saying so would send a
        // beginner indoors on a perfectly good night.
        night("2026-09-05", {
          moon_illumination: 0.99,
          best: { ...night("2026-09-05").best!, moon_up_fraction: 0.0 },
        }),
      ],
    }));
    renderCard();

    await waitFor(() =>
      expect(screen.getByTestId("plan-week")).toBeInTheDocument());
    expect(screen.getByText("Moon 92%, up all night")).toBeInTheDocument();
    expect(screen.queryByText(/Moon 99%/)).not.toBeInTheDocument();
  });

  it("is honest when a big library was trimmed by the scan cap", async () => {
    vi.spyOn(client.api, "getPlanWeek").mockResolvedValue(plan({
      nights: [night("2026-09-04")],
      n_targets_considered: 40, n_targets_with_position: 57,
    }));
    renderCard();

    await waitFor(() =>
      expect(screen.getByTestId("plan-week")).toBeInTheDocument());
    expect(screen.getByText(/Looked at 40 of your 57/)).toBeInTheDocument();
  });

  it("self-hides entirely on a backend too old to know the endpoint", async () => {
    const spy = vi.spyOn(client.api, "getPlanWeek")
      .mockRejectedValue(new Error("404"));
    renderCard();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("plan-week")).not.toBeInTheDocument();
  });

  it("passes the page's altitude floor through, so the two agree", async () => {
    const spy = vi.spyOn(client.api, "getPlanWeek").mockResolvedValue(plan());
    renderCard({ minAlt: 45 });
    await waitFor(() => expect(spy).toHaveBeenCalledWith({ minAlt: 45 }));

    spy.mockClear();
    renderCard();
    await waitFor(() => expect(spy).toHaveBeenCalledWith(undefined));
  });
});
