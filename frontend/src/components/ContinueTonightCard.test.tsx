import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ContinueTonightCard } from "./ContinueTonightCard";
import type { NightPlan, PlannedTarget, TargetProgress } from "../api/client";
import * as client from "../api/client";

function owned(over: Partial<PlannedTarget> = {}): PlannedTarget {
  return {
    id: over.target_safe ?? "t",
    name: "M31",
    ra_deg: 10,
    dec_deg: 41,
    type: "Galaxy",
    con: "And",
    already_targeted: true,
    max_altitude_deg: 70,
    transit_utc: "2026-07-24T03:00:00+00:00",
    minutes_above_min_alt: 300,
    moon_separation_deg: 90,
    moon_up_fraction: 0,
    usable_start_utc: "2026-07-24T01:00:00+00:00",
    usable_end_utc: "2026-07-24T05:00:00+00:00",
    score: 60,
    target_safe: "m31",
    frames_accepted: 200,
    total_exposure_s: 4.5 * 3600,
    ...over,
  } as PlannedTarget;
}

function plan(targets: PlannedTarget[]): NightPlan {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    generated_utc: "2026-07-24T00:00:00Z",
    dark_window: {
      start_utc: "2026-07-24T21:30:00Z",
      end_utc: "2026-07-25T03:30:00Z",
      duration_minutes: 360,
      sun_alt_threshold_deg: -18,
    },
    moon_illumination: 0.2,
    moon_waxing: true,
    min_altitude_deg: 30,
    horizon_active: false,
    targets,
  } as unknown as NightPlan;
}

function renderCard() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <ContinueTonightCard />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("ContinueTonightCard", () => {
  it("recommends the started target closest to a finished picture", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(
      plan([
        owned({ name: "M81", target_safe: "m81", total_exposure_s: 1 * 3600, score: 90 }),
        owned({ name: "M31", target_safe: "m31", total_exposure_s: 4.5 * 3600, score: 50 }),
      ]),
    );
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([]);
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Point here tonight")).toBeInTheDocument(),
    );
    // M31 (4.5 h of 6 h goal) wins over M81 (1 h) despite the lower score.
    expect(screen.getByText("M31")).toBeInTheDocument();
    expect(screen.getByText(/200 subs/)).toBeInTheDocument();
    // M81 appears as a dimmed runner-up.
    expect(screen.getByText("Or continue:")).toBeInTheDocument();
    expect(screen.getByText("M81")).toBeInTheDocument();
  });

  it("self-hides when no location / no started target is up tonight", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(
      plan([owned({ target_safe: "m31", score: 0 })]), // never clears the floor
    );
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue([]);
    const { container } = renderCard();
    await waitFor(() => expect(client.api.getTonight).toHaveBeenCalled());
    expect(container.querySelector(".mantine-Paper-root")).toBeNull();
  });

  it("honours a user-set integration goal from library-progress", async () => {
    // M31 at 4.5 h: default 6 h goal → improvable and it would be the pick. With
    // a user goal of 4 h it's already 'plenty' → excluded, leaving M81.
    vi.spyOn(client.api, "getTonight").mockResolvedValue(
      plan([
        owned({ name: "M31", target_safe: "m31", total_exposure_s: 4.5 * 3600, score: 50 }),
        owned({ name: "M81", target_safe: "m81", total_exposure_s: 1 * 3600, score: 90 }),
      ]),
    );
    const progress: TargetProgress[] = [
      { safe: "m31", name: "M31", total_exposure_s: 4.5 * 3600, object_type: "Galaxy", goal_s: 4 * 3600 },
    ];
    vi.spyOn(client.api, "getLibraryProgress").mockResolvedValue(progress);
    renderCard();
    await waitFor(() =>
      expect(screen.getByText("Point here tonight")).toBeInTheDocument(),
    );
    // Heading M81 is the pick; M31 must not be the headline (no runner-up here).
    expect(screen.getByText("M81")).toBeInTheDocument();
    expect(screen.queryByText("M31")).toBeNull();
  });
});
