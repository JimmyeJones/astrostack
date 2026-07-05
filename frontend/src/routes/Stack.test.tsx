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
      dark_master_id: 1, flat_master_id: null, flat_dark_master_id: null, bias_master_id: null,
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

  it("nudges when masters exist but nothing is selected, then hides once applied", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 1, name: "Dark 30s", kind: "dark", filename: "d1.fits", n_frames: 20,
        method: "median", exposure_s: 30, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
      { id: 3, name: "Flat", kind: "flat", filename: "f3.fits", n_frames: 20,
        method: "median", exposure_s: 2, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 30, gain: 80, sensor_temp_c: null },
      dark_master_id: 1, flat_master_id: 3, flat_dark_master_id: null, bias_master_id: null,
      scores: { "1": 1, "3": 1 }, n_frames: 12,
    });

    renderStack();

    // The prominent "you have masters but aren't using them" nudge names both
    // recommended kinds while nothing is selected.
    await waitFor(() =>
      expect(screen.getByText(/matching master dark \+ flat in your library/)).toBeInTheDocument());

    fireEvent.click(screen.getByText("Use recommended"));
    // Once applied, the nudge (and the apply button) are gone.
    await waitFor(() =>
      expect(screen.queryByText(/isn't calibrated/)).not.toBeInTheDocument());
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
      dark_master_id: 1, flat_master_id: 3, flat_dark_master_id: 2, bias_master_id: null,
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
      dark_master_id: 2, flat_master_id: null, flat_dark_master_id: null, bias_master_id: null,
      scores: { "1": 1, "2": 0.2 }, n_frames: 12,
    });

    renderStack();

    await waitFor(() => expect(screen.getByText("Use recommended")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Use recommended"));
    await waitFor(() =>
      expect(screen.getByText(/shot at 120s but your subs are 30s/)).toBeInTheDocument());
  });

  it("offers a one-click dark exposure-scaling when a bias is also selected, then confirms", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    // A mismatched 120 s dark and a master bias both already selected.
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue(
      { dark_master_id: 2, bias_master_id: 3 });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 2, name: "Dark 120s", kind: "dark", filename: "d2.fits", n_frames: 20,
        method: "median", exposure_s: 120, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
      { id: 3, name: "Bias", kind: "bias", filename: "b.fits", n_frames: 20,
        method: "median", exposure_s: 0, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    // Subs are 30 s (from the suggestion params) → the 120 s dark is a mismatch.
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 30, gain: 80, sensor_temp_c: null },
      dark_master_id: null, flat_master_id: null, flat_dark_master_id: null, bias_master_id: null,
      scores: {}, n_frames: 12,
    });

    renderStack();

    const btn = await screen.findByRole(
      "button", { name: "Scale this dark to your subs' exposure" });
    fireEvent.click(btn);
    // The yellow mismatch warning is replaced by the teal "scaling is on" note.
    await waitFor(() =>
      expect(screen.getByText(/Dark exposure-scaling is on/)).toBeInTheDocument());
    expect(screen.queryByText(/shot at 120s but your subs are 30s/)).not.toBeInTheDocument();
  });

  it("proactively offers to select an available bias and scale the dark, then confirms", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    // A mismatched 120 s dark selected but NO bias selected yet — the library
    // holds one, so scaling should be one click (pick the bias + flip the flag).
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ dark_master_id: 2 });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 2, name: "Dark 120s", kind: "dark", filename: "d2.fits", n_frames: 20,
        method: "median", exposure_s: 120, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
      { id: 3, name: "Bias", kind: "bias", filename: "b.fits", n_frames: 20,
        method: "median", exposure_s: 0, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 30, gain: 80, sensor_temp_c: null },
      dark_master_id: null, flat_master_id: null, flat_dark_master_id: null, bias_master_id: 3,
      scores: {}, n_frames: 12,
    });

    renderStack();

    const btn = await screen.findByRole(
      "button", { name: "Select your master bias and scale the dark" });
    fireEvent.click(btn);
    // Selecting the bias + enabling scaling replaces the yellow warning with the
    // teal "scaling is on" confirmation.
    await waitFor(() =>
      expect(screen.getByText(/Dark exposure-scaling is on/)).toBeInTheDocument());
    expect(screen.queryByText(/shot at 120s but your subs are 30s/)).not.toBeInTheDocument();
  });

  it("does not offer the bias-scaling nudge when the library has no bias", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ dark_master_id: 2 });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 2, name: "Dark 120s", kind: "dark", filename: "d2.fits", n_frames: 20,
        method: "median", exposure_s: 120, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 30, gain: 80, sensor_temp_c: null },
      dark_master_id: null, flat_master_id: null, flat_dark_master_id: null, bias_master_id: null,
      scores: {}, n_frames: 12,
    });

    renderStack();

    // The mismatch warning still shows (with prose to add a bias), but there's no
    // one-click nudge because there's no bias to select.
    await waitFor(() =>
      expect(screen.getByText(/shot at 120s but your subs are 30s/)).toBeInTheDocument());
    expect(screen.queryByRole(
      "button", { name: "Select your master bias and scale the dark" })).not.toBeInTheDocument();
  });

  function mkFrame(id: number): client.Frame {
    return {
      id, name: `f${id}.fits`, timestamp_utc: null, exposure_s: 30, gain: 80,
      width_px: 480, height_px: 320, bayer_pattern: "RGGB", solved: true,
      ra_center_deg: null, dec_center_deg: null, ra_hint_deg: null, dec_hint_deg: null,
      fwhm_px: null, star_count: null, sky_adu_median: null, eccentricity_median: null,
      transparency_score: null,
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

  it("turns off sigma-clip in one click from the low-frame caution, then hides it", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2), mkFrame(3)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    const btn = await screen.findByRole("button", { name: "Turn off sigma clipping" });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.queryByText(/only have 3 accepted, solved frames/)).not.toBeInTheDocument());
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
    // sigma_clip off → no per-pixel rejection. Use ≥11 frames so the generic
    // "turn on sigma clipping" advice is the right one (below ~11 the min/max
    // hint supersedes it — covered separately below).
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: false });
    const frames = Array.from({ length: 12 }, (_, i) =>
      ({ ...mkFrame(i + 1), streak_detected: i === 0 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/detected satellite\/plane streak/)).toBeInTheDocument());
  });

  it("suggests min/max reject for a small streaked stack (κ-σ can't handle it)", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    // 6 accepted frames (small, ≥3) with a streak and min/max reject off.
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true, min_max_reject: false });
    const frames = Array.from({ length: 6 }, (_, i) =>
      ({ ...mkFrame(i + 1), streak_detected: i === 0 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/Min\/max rejection.*drops the single highest and lowest/))
        .toBeInTheDocument());
  });

  it("turns on min/max reject in one click from the nudge, then hides the nudge", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true, min_max_reject: false });
    const frames = Array.from({ length: 6 }, (_, i) =>
      ({ ...mkFrame(i + 1), streak_detected: i === 0 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    const btn = await screen.findByRole("button", { name: "Turn on min/max rejection" });
    fireEvent.click(btn);
    // The nudge (and its button) disappear once min/max reject is on.
    await waitFor(() =>
      expect(screen.queryByText(/drops the single highest and lowest/)).not.toBeInTheDocument());
  });

  it("does not suggest min/max reject when it is already on", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ min_max_reject: true });
    const frames = Array.from({ length: 6 }, (_, i) =>
      ({ ...mkFrame(i + 1), streak_detected: i === 0 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    // Wait until the *defaults* have actually applied (the min/max reject switch
    // reads as on), not just until the schema-driven label renders — otherwise the
    // nudge shows transiently between the schema and defaults queries resolving and
    // this negative assertion races it (a CI flake). Once the switch is checked the
    // "already on" suppression is in effect, so the nudge must be absent.
    const toggle = await screen.findByLabelText("Min/max rejection");
    await waitFor(() => expect(toggle).toBeChecked());
    expect(screen.queryByText(/drops the single highest and lowest/)).not.toBeInTheDocument();
  });

  it("does not suggest min/max reject on a large streaked stack", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    // 20 frames — above the ~11-frame threshold, so κ-σ can handle it.
    const frames = Array.from({ length: 20 }, (_, i) =>
      ({ ...mkFrame(i + 1), streak_detected: i === 0 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() => expect(screen.getByText("Sigma clipping")).toBeInTheDocument());
    expect(screen.queryByText(/drops the single highest and lowest/)).not.toBeInTheDocument();
  });

  it("warns when the min/max reject k is too high for the frame count", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "min_max_reject_count", label: "Min/max reject count", type: "int", group: "advanced",
        default: 1, min: 1, max: 5, step: 1, options: null, help: null, depends_on: "min_max_reject" },
    ]);
    // 6 accepted frames with k=3 → needs 7+ per pixel, so it can't fully apply.
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ min_max_reject: true, min_max_reject_count: 3 });
    const frames = Array.from({ length: 6 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/needs at least 7 frames per pixel to fully apply/))
        .toBeInTheDocument());
  });

  it("lowers k in one click from the too-high nudge, then hides it", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "min_max_reject_count", label: "Min/max reject count", type: "int", group: "advanced",
        default: 1, min: 1, max: 5, step: 1, options: null, help: null, depends_on: "min_max_reject" },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ min_max_reject: true, min_max_reject_count: 3 });
    const frames = Array.from({ length: 6 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    // 6 frames → largest fully-applicable k is 2.
    const btn = await screen.findByRole("button", { name: "Lower k to 2" });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.queryByText(/needs at least 7 frames per pixel/)).not.toBeInTheDocument());
  });

  it("does not warn when the min/max reject k fits the frame count", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "min_max_reject_count", label: "Min/max reject count", type: "int", group: "advanced",
        default: 1, min: 1, max: 5, step: 1, options: null, help: null, depends_on: "min_max_reject" },
    ]);
    // 8 frames with k=3 → 2·3+1 = 7 ≤ 8, so it fully applies; no warning.
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ min_max_reject: true, min_max_reject_count: 3 });
    const frames = Array.from({ length: 8 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() => expect(screen.getByText("Min/max rejection")).toBeInTheDocument());
    expect(screen.queryByText(/frames per pixel to fully apply/)).not.toBeInTheDocument();
  });

  it("suggests raising k to the streaked-frame count when min/max reject is on", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "min_max_reject_count", label: "Min/max reject count", type: "int", group: "advanced",
        default: 1, min: 1, max: 5, step: 1, options: null, help: null, depends_on: "min_max_reject" },
    ]);
    // 12 accepted frames, 3 of them streaked, min/max reject on with default k=1.
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ min_max_reject: true, min_max_reject_count: 1 });
    const frames = Array.from({ length: 12 }, (_, i) =>
      ({ ...mkFrame(i + 1), streak_detected: i < 3 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    // 3 streaked frames → suggest k=3 (well within the 12-frame budget).
    const btn = await screen.findByRole("button", { name: "Set k = 3" });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.queryByText(/carry a satellite\/plane streak/)).not.toBeInTheDocument());
  });

  it("caps the suggested k at what the frame count can fully apply", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "min_max_reject_count", label: "Min/max reject count", type: "int", group: "advanced",
        default: 1, min: 1, max: 5, step: 1, options: null, help: null, depends_on: "min_max_reject" },
    ]);
    // 4 streaked frames but only 7 solved → largest fully-applicable k is 3, not 4.
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ min_max_reject: true, min_max_reject_count: 1 });
    const frames = Array.from({ length: 7 }, (_, i) =>
      ({ ...mkFrame(i + 1), streak_detected: i < 4 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await screen.findByRole("button", { name: "Set k = 3" });
    expect(screen.queryByRole("button", { name: "Set k = 4" })).not.toBeInTheDocument();
  });

  it("does not suggest raising k when only one frame is streaked", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "min_max_reject_count", label: "Min/max reject count", type: "int", group: "advanced",
        default: 1, min: 1, max: 5, step: 1, options: null, help: null, depends_on: "min_max_reject" },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ min_max_reject: true, min_max_reject_count: 1 });
    const frames = Array.from({ length: 12 }, (_, i) =>
      ({ ...mkFrame(i + 1), streak_detected: i === 0 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() => expect(screen.getByText("Min/max rejection")).toBeInTheDocument());
    expect(screen.queryByText(/carry a satellite\/plane streak/)).not.toBeInTheDocument();
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

  it("flags a hazy stack whose transparency sits below the target baseline", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    // Target's clear-sky baseline is ~10000; the accepted+solved run frames are
    // all hazy (~3000), well below 0.6× the 90th-percentile baseline.
    const clear = Array.from({ length: 5 }, (_, i) =>
      ({ ...mkFrame(100 + i), accept: false, transparency_score: 10000 }));
    const hazy = Array.from({ length: 5 }, (_, i) =>
      ({ ...mkFrame(i + 1), transparency_score: 3000 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue([...clear, ...hazy]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/likely shot through haze or thin cloud/)).toBeInTheDocument());
  });

  it("does not flag transparency when the run matches the target baseline", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    const frames = Array.from({ length: 8 }, (_, i) =>
      ({ ...mkFrame(i + 1), transparency_score: 9000 + i * 10 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() => expect(screen.getByText("Start stacking")).toBeInTheDocument());
    expect(screen.queryByText(/likely shot through haze or thin cloud/)).not.toBeInTheDocument();
  });

  it("nudges quality weighting when frame quality varies a lot", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ quality_weighted: false });
    // A wide FWHM spread across accepted+solved frames (2.0 … 5.0px).
    const frames = Array.from({ length: 8 }, (_, i) =>
      ({ ...mkFrame(i + 1), fwhm_px: 2.0 + i * 0.4 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/mixed-quality set is exactly where quality weighting helps/))
        .toBeInTheDocument());
  });

  it("turns on quality weighting in one click from the mixed-quality nudge, then hides it", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ quality_weighted: false });
    const frames = Array.from({ length: 8 }, (_, i) =>
      ({ ...mkFrame(i + 1), fwhm_px: 2.0 + i * 0.4 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    const btn = await screen.findByRole("button", { name: "Turn on quality weighting" });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.queryByText(/mixed-quality set is exactly where/)).not.toBeInTheDocument());
  });

  it("offers a one-click quality-weighting button on the hazy-transparency hint", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ quality_weighted: false });
    const clear = Array.from({ length: 5 }, (_, i) =>
      ({ ...mkFrame(100 + i), accept: false, transparency_score: 10000 }));
    const hazy = Array.from({ length: 5 }, (_, i) =>
      ({ ...mkFrame(i + 1), transparency_score: 3000 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue([...clear, ...hazy]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    // The hint carries a one-click button; clicking it turns quality weighting on,
    // so the (quality_weighted-guarded) button disappears while the hint text stays.
    const btn = await screen.findByRole("button", { name: "Turn on quality weighting" });
    expect(screen.getByText(/likely shot through haze or thin cloud/)).toBeInTheDocument();
    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Turn on quality weighting" }))
        .not.toBeInTheDocument());
    // The advisory itself remains — turning on weighting doesn't un-haze the data.
    expect(screen.getByText(/likely shot through haze or thin cloud/)).toBeInTheDocument();
  });

  it("does not nudge quality weighting when the set is uniform", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ quality_weighted: false });
    const frames = Array.from({ length: 8 }, (_, i) =>
      ({ ...mkFrame(i + 1), fwhm_px: 2.5 + i * 0.01, star_count: 300 + i }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() => expect(screen.getByText("Start stacking")).toBeInTheDocument());
    expect(screen.queryByText(/mixed-quality set is exactly where/)).not.toBeInTheDocument();
  });

  it("nudges photometric normalization when transparency varies a lot, then hides once on", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ photometric_normalize: false });
    // A wide transparency spread across the frames-to-be-stacked (2000 … 9000),
    // so p90/p10 ≫ 1.5 — haze / airmass varying across nights.
    const frames = Array.from({ length: 8 }, (_, i) =>
      ({ ...mkFrame(i + 1), transparency_score: 2000 + i * 1000 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    const btn = await screen.findByRole("button", { name: "Turn on photometric normalization" });
    expect(screen.getByText(/vary a lot in transparency/)).toBeInTheDocument();
    // One click turns the option on and the nudge disappears.
    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.queryByText(/vary a lot in transparency/)).not.toBeInTheDocument());
  });

  it("does not nudge photometric normalization when transparency is uniform", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ photometric_normalize: false });
    // Tight transparency (all ~5000) → p90/p10 ≈ 1, well under the 1.5 trigger.
    const frames = Array.from({ length: 8 }, (_, i) =>
      ({ ...mkFrame(i + 1), transparency_score: 5000 + i * 10 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() => expect(screen.getByText("Start stacking")).toBeInTheDocument());
    expect(screen.queryByText(/vary a lot in transparency/)).not.toBeInTheDocument();
  });

  it("does not nudge photometric normalization when it is already on", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ photometric_normalize: true });
    const frames = Array.from({ length: 8 }, (_, i) =>
      ({ ...mkFrame(i + 1), transparency_score: 2000 + i * 1000 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() => expect(screen.getByText("Start stacking")).toBeInTheDocument());
    expect(screen.queryByText(/vary a lot in transparency/)).not.toBeInTheDocument();
  });

  it("hints to review auto-grade when accepted frames look like outliers", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    const frames = Array.from({ length: 12 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "autoGradePreview").mockResolvedValue({
      sensitivity: "normal", n_accepted: 12, n_considered: 12,
      recommendations: [
        { frame_id: 1, name: "f1.fits", reasons: [
          { metric: "star_count", label: "far fewer stars than typical", value: 20, typical: 300, z: 8 },
        ] },
        { frame_id: 2, name: "f2.fits", reasons: [
          { metric: "fwhm_px", label: "much softer than typical", value: 6, typical: 2.5, z: 7 },
        ] },
      ],
      metrics_used: ["fwhm_px", "star_count"], metrics_skipped: {},
      capped: false, changed_ids: null,
    });

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/Auto-grade thinks 2 of your 12 accepted frames look like quality outliers/))
        .toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Review Auto-grade" }))
      .toHaveAttribute("href", "/targets/M_42");
  });

  it("does not hint auto-grade when nothing is flagged", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    const frames = Array.from({ length: 12 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "autoGradePreview").mockResolvedValue({
      sensitivity: "normal", n_accepted: 12, n_considered: 12,
      recommendations: [], metrics_used: ["fwhm_px"], metrics_skipped: {},
      capped: false, changed_ids: null,
    });

    renderStack();

    await waitFor(() => expect(screen.getByText("Start stacking")).toBeInTheDocument());
    expect(screen.queryByText(/look like quality outliers/)).not.toBeInTheDocument();
  });

  it("drops the auto-grade outliers in one click and offers an undo", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    const frames = Array.from({ length: 12 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "autoGradePreview").mockResolvedValue({
      sensitivity: "normal", n_accepted: 12, n_considered: 12,
      recommendations: [
        { frame_id: 1, name: "f1.fits", reasons: [
          { metric: "star_count", label: "far fewer stars than typical", value: 20, typical: 300, z: 8 },
        ] },
        { frame_id: 2, name: "f2.fits", reasons: [
          { metric: "fwhm_px", label: "much softer than typical", value: 6, typical: 2.5, z: 7 },
        ] },
      ],
      metrics_used: ["fwhm_px", "star_count"], metrics_skipped: {},
      capped: false, changed_ids: null,
    });
    const apply = vi.spyOn(client.api, "autoGradeApply").mockResolvedValue({
      sensitivity: "normal", n_accepted: 12, n_considered: 12,
      recommendations: [], metrics_used: ["fwhm_px", "star_count"], metrics_skipped: {},
      capped: false, changed_ids: [1, 2],
    });
    const bulk = vi.spyOn(client.api, "bulkFrames").mockResolvedValue({ changed: 2, changed_ids: [1, 2] });

    renderStack();

    const drop = await screen.findByRole("button", { name: "Drop 2 outlier frames" });
    fireEvent.click(drop);

    // After applying, the yellow nudge is replaced by a green confirmation + undo.
    await waitFor(() => expect(screen.getByText(/Dropped 2 outlier frames/)).toBeInTheDocument());
    expect(apply).toHaveBeenCalledWith("M_42");
    expect(screen.queryByRole("button", { name: "Drop 2 outlier frames" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Undo — re-accept 2 frames" }));
    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", { action: "accept", ids: [1, 2] }));
  });

  it("surfaces the auto-grade safety cap in the Stack-form hint", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    const frames = Array.from({ length: 20 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "autoGradePreview").mockResolvedValue({
      sensitivity: "normal", n_accepted: 20, n_considered: 20,
      recommendations: [
        { frame_id: 1, name: "f1.fits", reasons: [
          { metric: "sky_level", label: "much brighter sky than typical", value: 900, typical: 200, z: 9 },
        ] },
      ],
      metrics_used: ["sky_level"], metrics_skipped: {},
      capped: true, changed_ids: null,
    });

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/only the worst are recommended; review before stacking/))
        .toBeInTheDocument());
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
      suggested_drizzle_scale: null, suggested_reference_canvas: false,
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
      suggested_drizzle_scale: null, suggested_reference_canvas: false,
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
      suggested_drizzle_scale: 1.4, suggested_reference_canvas: false,
    });

    renderStack();

    const btn = await screen.findByRole("button", { name: /Use drizzle ×1.4 instead/ });
    fireEvent.click(btn);
    // Clicking sets the form's drizzle_scale so the next estimate re-queries.
    await waitFor(() =>
      expect(client.api.stackEstimate).toHaveBeenCalledWith(
        "M_42", expect.objectContaining({ drizzle_scale: 1.4 })));
  });

  it("offers the reference canvas when a non-drizzle mosaic is over budget", async () => {
    vi.spyOn(client.api, "optionsSchema").mockResolvedValue([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue({
      n_frames: 2, canvas_w: 8000, canvas_h: 6000, output_w: 8000, output_h: 6000,
      is_mosaic: true, peak_bytes: 2.3e9, peak_gb: 2.3,
      budget_bytes: 1.4e9, budget_gb: 1.4, would_exceed: true,
      suggested_drizzle_scale: null, suggested_reference_canvas: true,
    });

    renderStack();

    const btn = await screen.findByRole("button", { name: /Use the reference canvas instead/ });
    fireEvent.click(btn);
    // Clicking switches mosaic_canvas → reference so the next estimate re-queries.
    await waitFor(() =>
      expect(client.api.stackEstimate).toHaveBeenCalledWith(
        "M_42", expect.objectContaining({ mosaic_canvas: "reference" })));
  });
});
