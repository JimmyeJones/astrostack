import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("plans a chosen future night by passing the date to the API", async () => {
    const spy = vi.spyOn(client.api, "getTonight").mockResolvedValue(plan({}));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText("Add more to what you're shooting")).toBeInTheDocument());
    // Initial fetch plans tonight — no date param.
    expect(spy).toHaveBeenLastCalledWith(expect.not.objectContaining({ date: expect.anything() }));

    // Picking a future date refetches with that date and renames the sections.
    const future = "2026-08-15";
    fireEvent.change(screen.getByLabelText("Night"), { target: { value: future } });
    await waitFor(() =>
      expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ date: future })));
    await waitFor(() =>
      expect(screen.getByText(/Start something new on/)).toBeInTheDocument());
    // A "Tonight" reset clears the date back to tonight.
    fireEvent.click(screen.getByRole("button", { name: "Tonight" }));
    await waitFor(() =>
      expect(screen.getByText("Start something new tonight")).toBeInTheDocument());
  });

  it("filters 'start something new' by object type", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(plan({
      targets: [
        target({ id: "M31", name: "Andromeda", type: "galaxy", already_targeted: false, score: 80 }),
        target({ id: "M42", name: "Orion Nebula", type: "nebula", already_targeted: false, score: 70 }),
        target({ id: "M13", name: "Hercules", type: "globular cluster", already_targeted: false, score: 60 }),
      ],
    }));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText("Start something new tonight")).toBeInTheDocument());
    // All three show initially.
    expect(screen.getByText(/M31/)).toBeInTheDocument();
    expect(screen.getByText(/M42/)).toBeInTheDocument();
    expect(screen.getByText(/M13/)).toBeInTheDocument();
    // Picking "Nebula" keeps only the nebula.
    fireEvent.click(screen.getByRole("radio", { name: "Nebula" }));
    await waitFor(() => expect(screen.queryByText(/M31/)).not.toBeInTheDocument());
    expect(screen.getByText(/M42/)).toBeInTheDocument();
    expect(screen.queryByText(/M13/)).not.toBeInTheDocument();
  });

  it("falls back to All (not an empty table) when the picked type vanishes after a data change", async () => {
    const spy = vi.spyOn(client.api, "getTonight")
      .mockResolvedValueOnce(plan({
        targets: [
          target({ id: "M31", name: "Andromeda", type: "galaxy", already_targeted: false, score: 80 }),
          target({ id: "M42", name: "Orion Nebula", type: "nebula", already_targeted: false, score: 70 }),
        ],
      }))
      .mockResolvedValue(plan({
        // A different night: only a galaxy is up, so the previously-picked "Nebula" bucket is gone.
        targets: [
          target({ id: "M81", name: "Bode's Galaxy", type: "galaxy", already_targeted: false, score: 75 }),
        ],
      }));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText("Start something new tonight")).toBeInTheDocument());
    // Pick Nebula while it's available.
    fireEvent.click(screen.getByRole("radio", { name: "Nebula" }));
    await waitFor(() => expect(screen.queryByText(/M31/)).not.toBeInTheDocument());
    expect(screen.getByText(/M42/)).toBeInTheDocument();

    // Re-plan a night whose fresh data has no nebula — the stale "Nebula"
    // selection must fall back to All rather than filtering the table to empty.
    fireEvent.change(screen.getByLabelText("Night"), { target: { value: "2026-08-15" } });
    await waitFor(() =>
      expect(spy).toHaveBeenLastCalledWith(expect.objectContaining({ date: "2026-08-15" })));
    await waitFor(() => expect(screen.getByText(/M81/)).toBeInTheDocument());
    expect(screen.queryByText(/No targets of that type/)).not.toBeInTheDocument();
  });

  it("hides the type filter when only one object type is present", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(plan({
      targets: [
        target({ id: "M31", type: "galaxy", already_targeted: false, score: 80 }),
        target({ id: "M81", type: "galaxy", already_targeted: false, score: 70 }),
      ],
    }));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText("Start something new tonight")).toBeInTheDocument());
    expect(screen.queryByRole("radio", { name: "Galaxy" })).not.toBeInTheDocument();
  });

  it("hides targets that aren't up tonight behind a dimmed count", async () => {
    // The planner returns every catalog object regardless of observability;
    // ones that never clear the floor (minutes_above_min_alt 0) are dead rows.
    vi.spyOn(client.api, "getTonight").mockResolvedValue(plan({
      targets: [
        target({ id: "M13", name: "Up Now", already_targeted: false, score: 65,
                 minutes_above_min_alt: 180 }),
        target({ id: "M99", name: "Not Up", already_targeted: false, score: 0,
                 minutes_above_min_alt: 0 }),
      ],
    }));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText("Start something new tonight")).toBeInTheDocument());
    // The observable target is listed; the not-up one is not a table row.
    expect(screen.getByText(/M13/)).toBeInTheDocument();
    expect(screen.queryByText(/M99/)).not.toBeInTheDocument();
    // A dimmed footnote accounts for the hidden target with a way to reveal it.
    expect(screen.getByText(/1 more target isn't up tonight/)).toBeInTheDocument();
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

  it("nudges a well-integrated library target toward something new", async () => {
    vi.spyOn(client.api, "getTonight").mockResolvedValue(plan({
      targets: [
        // 7 h on a galaxy (6 h goal) → past the goal → "try something new".
        target({ id: "M31", name: "Andromeda", type: "galaxy", already_targeted: true,
                 target_safe: "M_31", frames_accepted: 200, total_exposure_s: 7 * 3600, score: 80 }),
        // 1 h on a galaxy → still worth topping up → no nudge.
        target({ id: "M81", name: "Bode's", type: "galaxy", already_targeted: true,
                 target_safe: "M_81", frames_accepted: 40, total_exposure_s: 3600, score: 70 }),
      ],
    }));
    renderTonight();
    await waitFor(() =>
      expect(screen.getByText("Add more to what you're shooting")).toBeInTheDocument());
    expect(screen.getByText("Plenty — try something new")).toBeInTheDocument();
    // The barely-started target gets no readiness nudge.
    expect(screen.queryByText("Nearly there")).not.toBeInTheDocument();
  });
});
