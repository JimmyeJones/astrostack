import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TonightView } from "./Tonight";
import * as client from "../api/client";
import type { NightPlan, PlannedTarget } from "../api/client";

function target(over: Partial<PlannedTarget>): PlannedTarget {
  return {
    id: "M42", name: "Orion Nebula", ra_deg: 83.8, dec_deg: -5.4, type: "nebula",
    con: "Ori", already_targeted: false, max_altitude_deg: 40,
    transit_utc: "2026-01-15T22:00:00+00:00", minutes_above_min_alt: 180,
    moon_separation_deg: 60, score: 55, target_safe: null,
    frames_accepted: null, total_exposure_s: null, ...over,
  };
}

function plan(over: Partial<NightPlan>): NightPlan {
  return {
    location_source: "settings",
    observer: { lat_deg: 51.5, lon_deg: -0.13, elevation_m: 30 },
    generated_utc: "2026-01-15T20:00:00+00:00",
    dark_window: {
      start_utc: "2026-01-15T18:23:00+00:00", end_utc: "2026-01-16T05:55:00+00:00",
      duration_minutes: 692, sun_alt_threshold_deg: -18,
    },
    moon_illumination: 0.08, min_altitude_deg: 30, targets: [], ...over,
  };
}

function renderTonight() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><TonightView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("TonightView", () => {
  it("prompts for a location when none is known", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(
      plan({ location_source: "none", observer: null, dark_window: null, moon_illumination: null }));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText("Set your observing location")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /Settings/i }))
      .toHaveAttribute("href", "/settings");
  });

  it("explains a polar-day night with no dark window", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(plan({ dark_window: null }));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText("No darkness tonight")).toBeInTheDocument());
  });

  it("labels the Moon card with its waxing/waning state", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(plan({
      moon_illumination: 0.72, moon_waxing: false,
    }));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText("Waning gibbous (72%)")).toBeInTheDocument());
  });

  it("shows the Moon's rise/set time under the phase when it crosses the night", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(plan({
      moon_illumination: 0.47, moon_waxing: true,
      moon_window: {
        rise_utc: null, set_utc: "2026-01-16T01:03:00+00:00",
        up_all_night: false, down_all_night: false,
      },
    }));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText(/sets ~/i)).toBeInTheDocument());
    // The generic "nearer + brighter" hint is replaced by the concrete cue.
    expect(screen.queryByText(/Nearer \+ brighter/i)).not.toBeInTheDocument();
  });

  it("guides a first-timer with no library targets instead of blaming altitude", async () => {
    // No library targets => the "already targeted" table is empty, but the
    // reason is an empty library, not the altitude floor.
    vi.spyOn(client.api, "getTonight").mockResolvedValue(plan({
      targets: [target({ id: "M13", already_targeted: false, score: 65 })],
    }));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText("Add more to what you're shooting")).toBeInTheDocument());
    expect(screen.getByText(/haven't shot any targets/i)).toBeInTheDocument();
    // The catalog section still lists its suggestion.
    expect(screen.getByText(/M13/)).toBeInTheDocument();
  });

  it("shows the active minimum-altitude floor even when it isn't a round preset", async () => {
    // A 45° floor is reachable from the step-5 Settings input but isn't one of
    // the picker's presets — the Select must still render it, not blank out.
    vi.spyOn(client.api, "getTonight").mockResolvedValue(plan({ min_altitude_deg: 45 }));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText("Add more to what you're shooting")).toBeInTheDocument());
    // The visible Select input shows the option's label ("45°"); before the fix
    // there was no matching option for a 45° floor and it rendered blank.
    expect(screen.getByDisplayValue("45°")).toBeInTheDocument();
  });

  it("ranks library targets and fresh catalog suggestions separately", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(plan({
      targets: [
        target({ id: "M31", name: "Andromeda Galaxy", already_targeted: true,
                 target_safe: "M_31", frames_accepted: 42, total_exposure_s: 4200, score: 80 }),
        target({ id: "M13", name: "Hercules Cluster", already_targeted: false, score: 65 }),
      ],
    }));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText("Add more to what you're shooting")).toBeInTheDocument());
    expect(screen.getByText("Start something new tonight")).toBeInTheDocument();
    // Library target links to its target page; catalog one does not.
    expect(screen.getByRole("link", { name: /M31 — Andromeda Galaxy/ }))
      .toHaveAttribute("href", "/targets/M_31");
    expect(screen.getByText(/M13 — Hercules Cluster/)).toBeInTheDocument();
    // The dark-window summary card shows the twilight kind.
    expect(screen.getByText(/astronomical/)).toBeInTheDocument();
  });
});
