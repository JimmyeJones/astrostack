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

  function mkFrame(id: number): client.Frame {
    return {
      id, name: `f${id}.fits`, timestamp_utc: null, exposure_s: 30, gain: 80,
      width_px: 480, height_px: 320, bayer_pattern: "RGGB", solved: true,
      ra_center_deg: null, dec_center_deg: null, ra_hint_deg: null, dec_hint_deg: null,
      fwhm_px: null, star_count: null, sky_adu_median: null, eccentricity_median: null,
      streak_detected: false, accept: true, reject_reason: null, user_override: false,
    };
  }

  it("cautions when sigma-clip is on but too few frames are accepted", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    // Only 3 accepted, solved frames — below the ~5 sigma-clip needs.
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2), mkFrame(3)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/only have 3 accepted, solved frames/)).toBeInTheDocument());
  });

  it("does not caution when enough frames are accepted for sigma-clip", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    const frames = Array.from({ length: 8 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() => expect(screen.getByText("Sigma clipping")).toBeInTheDocument());
    expect(screen.queryByText(/it can reject real signal as an outlier/)).not.toBeInTheDocument();
  });

  it("hints to tighten kappa on a very large stack", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true, sigma_kappa: 3 });
    // 250 accepted, solved frames — well above the large-stack threshold.
    const frames = Array.from({ length: 250 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/tighter sigma-clip \(κ≈2.5\)/)).toBeInTheDocument());
  });

  it("does not hint to tighten kappa on a small stack", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true, sigma_kappa: 3 });
    const frames = Array.from({ length: 20 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() => expect(screen.getByText("Sigma clipping")).toBeInTheDocument());
    expect(screen.queryByText(/tighter sigma-clip/)).not.toBeInTheDocument();
  });

  it("warns when accepted streaked frames are stacked without rejection", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    // sigma_clip off → no per-pixel rejection.
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: false });
    const streaked = { ...mkFrame(1), streak_detected: true };
    vi.spyOn(client.api, "listFrames").mockResolvedValue([streaked, mkFrame(2), mkFrame(3)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/detected satellite\/plane streak/)).toBeInTheDocument());
  });

  it("drops the streak warning once rejection has enough frames", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    // 5 accepted frames (≥4) with sigma-clip on → rejection is active.
    const frames = Array.from({ length: 5 }, (_, i) =>
      ({ ...mkFrame(i + 1), streak_detected: i === 0 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() => expect(screen.getByText("Sigma clipping")).toBeInTheDocument());
    expect(screen.queryByText(/detected satellite\/plane streak/)).not.toBeInTheDocument();
  });

  const drizzleSchema: client.StackOptionField[] = [
    { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
      default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    { key: "drizzle", label: "Drizzle (super-resolution)", type: "bool", group: "simple",
      default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    { key: "drizzle_reject", label: "Drizzle outlier rejection", type: "bool", group: "simple",
      default: false, min: null, max: null, step: null, options: null, help: null, depends_on: "drizzle" },
  ];

  it("hints that sigma-clip doesn't cover drizzle until drizzle rejection is on", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue(drizzleSchema);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue(
      { sigma_clip: true, drizzle: true, drizzle_reject: false });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/doesn't apply to drizzle's single-pass/)).toBeInTheDocument());
  });

  it("drops the drizzle hint once outlier rejection is enabled", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue(drizzleSchema);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue(
      { sigma_clip: true, drizzle: true, drizzle_reject: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() =>
      expect(screen.getByText("Drizzle outlier rejection")).toBeInTheDocument());
    expect(screen.queryByText(/doesn't apply to drizzle's single-pass/)).not.toBeInTheDocument();
  });

  it("shows the pre-run output canvas + peak-memory estimate line", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue({
      n_frames: 2, canvas_w: 480, canvas_h: 320, output_w: 480, output_h: 320,
      is_mosaic: false, peak_bytes: 7e6, peak_gb: 0.01,
      budget_bytes: 8e9, budget_gb: 8, would_exceed: false,
      suggested_drizzle_scale: null,
    });

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/2 accepted, solved frames · output 480×320/)).toBeInTheDocument());
    expect(screen.getByText(/GB peak memory/)).toBeInTheDocument();
  });

  it("warns in red when the estimate exceeds the memory budget", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue({
      n_frames: 2, canvas_w: 8000, canvas_h: 6000, output_w: 16000, output_h: 12000,
      is_mosaic: true, peak_bytes: 5.4e9, peak_gb: 5.4,
      budget_bytes: 1.4e9, budget_gb: 1.4, would_exceed: true,
      suggested_drizzle_scale: null,
    });

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/over the ~1.4 GB budget/)).toBeInTheDocument());
  });

  it("offers a one-click smaller drizzle scale when one fits the budget", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({
      sigma_clip: true, drizzle: true, drizzle_scale: 2.0,
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue({
      n_frames: 2, canvas_w: 4000, canvas_h: 3000, output_w: 8000, output_h: 6000,
      is_mosaic: false, peak_bytes: 2.3e9, peak_gb: 2.3,
      budget_bytes: 1.4e9, budget_gb: 1.4, would_exceed: true,
      suggested_drizzle_scale: 1.4,
    });

    renderStack();

    const btn = await screen.findByRole("button", { name: /Use drizzle ×1.4 instead/ });
    fireEvent.click(btn);
    // Clicking sets the form's drizzle_scale so the next estimate re-queries.
    await waitFor(() =>
      expect(client.api.stackEstimate).toHaveBeenCalledWith(
        "M_42", expect.objectContaining({ drizzle_scale: 1.4 })));
  });
});
