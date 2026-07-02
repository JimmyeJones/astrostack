import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StackView } from "./Stack";
import * as client from "../api/client";

function renderStack() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/targets/M_42/stack"]}>
          <Routes>
            <Route path="/targets/:safe/stack" element={<StackView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("StackView", () => {
  it("renders simple fields from the schema and hides advanced behind a disclosure", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "drizzle_scale", label: "Drizzle scale", type: "float", group: "advanced",
        default: 1.5, min: 1, max: 4, step: 0.1, options: null, help: null, depends_on: "drizzle" },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true, drizzle_scale: 1.5 });

    renderStack();

    await waitFor(() => expect(screen.getByText("Sigma clipping")).toBeInTheDocument());
    // Advanced control's label exists in the DOM (inside the collapsed accordion panel).
    expect(screen.getByText("Advanced options")).toBeInTheDocument();
    expect(screen.getByText("Start stacking")).toBeInTheDocument();
  });

  it("badges and applies the recommended calibration masters", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 1, name: "Dark 30s", kind: "dark", filename: "d1.fits", n_frames: 20,
        method: "median", exposure_s: 30, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
      { id: 2, name: "Dark 120s", kind: "dark", filename: "d2.fits", n_frames: 20,
        method: "median", exposure_s: 120, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 30, gain: 80, sensor_temp_c: null },
      dark_master_id: 1, flat_master_id: null, flat_dark_master_id: null,
      scores: { "1": 1, "2": 0.5 }, n_frames: 12,
    });

    renderStack();

    // The recommended dark is badged and a one-click apply is offered.
    await waitFor(() => expect(screen.getByText("Use recommended")).toBeInTheDocument());
    expect(screen.getByText(/Dark 30s.*★ recommended/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Use recommended"));
    // Once applied, the hint disappears (nothing left to apply).
    await waitFor(() => expect(screen.queryByText("Use recommended")).not.toBeInTheDocument());
  });

  it("recommends and applies a matching flat-dark", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 1, name: "Dark 30s", kind: "dark", filename: "d1.fits", n_frames: 20,
        method: "median", exposure_s: 30, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
      { id: 2, name: "Dark 2s", kind: "dark", filename: "d2.fits", n_frames: 20,
        method: "median", exposure_s: 2, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
      { id: 3, name: "Flat 2s", kind: "flat", filename: "f3.fits", n_frames: 20,
        method: "median", exposure_s: 2, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 30, gain: 80, sensor_temp_c: null },
      dark_master_id: 1, flat_master_id: 3, flat_dark_master_id: 2,
      scores: { "1": 1, "2": 0.2, "3": 1 }, n_frames: 12,
    });

    renderStack();

    await waitFor(() => expect(screen.getByText("Use recommended")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Use recommended"));

    // Applying reveals the flat-dark select (it only shows once a flat is set)
    // and badges the exposure-matched 2 s dark as the recommended flat-dark.
    await waitFor(() =>
      expect(screen.getByText("Flat-dark (optional)")).toBeInTheDocument());
    expect(screen.getByText(/Dark 2s.*★ recommended/)).toBeInTheDocument();
    // Nothing left to apply → the hint is gone.
    expect(screen.queryByText("Use recommended")).not.toBeInTheDocument();
  });

  it("warns when a chosen dark's exposure is far from the subs", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 1, name: "Dark 30s", kind: "dark", filename: "d1.fits", n_frames: 20,
        method: "median", exposure_s: 30, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
      { id: 2, name: "Dark 120s", kind: "dark", filename: "d2.fits", n_frames: 20,
        method: "median", exposure_s: 120, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    // Applying a (deliberately) mismatched 120 s dark against 30 s subs.
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 30, gain: 80, sensor_temp_c: null },
      dark_master_id: 2, flat_master_id: null, flat_dark_master_id: null,
      scores: { "1": 1, "2": 0.2 }, n_frames: 12,
    });

    renderStack();

    await waitFor(() => expect(screen.getByText("Use recommended")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Use recommended"));
    await waitFor(() =>
      expect(screen.getByText(/shot at 120s but your subs are 30s/)).toBeInTheDocument());
  });
});
