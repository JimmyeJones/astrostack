import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { notifications } from "@mantine/notifications";
import { StackView } from "./Stack";
import * as client from "../api/client";
import { stackPlacementMismatches } from "../test/stackOptionPlacement";

/**
 * Mock `GET /api/stack/options` — and refuse a fixture that puts a control
 * somewhere the running app never does.
 *
 * `Stack.tsx` renders these descriptors through `StackOptionControl`, which
 * decides from `group` whether a field sits on the page or inside the collapsed
 * **Advanced options** accordion, from `type` which control appears, and from
 * `depends_on` whether it is greyed out. A hand-written fixture is free to get
 * any of those wrong, and the test would still pass while a real user found the
 * control somewhere else — exactly how v0.240.0 shipped an editor button no
 * beginner could see. Checking here, at the point every test hands its fixture
 * over, means the guard can't be bypassed by a fixture written later.
 *
 * Only placement is pinned; labels, defaults, bounds and help stay free, so a
 * fixture can still be a simplified stand-in (see `stackOptionPlacement.ts`).
 */
function mockSchema(fields: client.StackOptionField[]) {
  const problems = stackPlacementMismatches(fields);
  if (problems.length > 0) {
    throw new Error(
      `Stack option fixture doesn't match the engine's descriptors:\n  `
      + problems.join("\n  "));
  }
  return vi.spyOn(client.api, "optionsSchema").mockResolvedValue(fields);
}


function renderStackAt(path: string) {
  // Retries off so a deliberately-rejected query fails fast (no exponential
  // backoff) in tests that exercise error paths.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/targets/:safe/stack" element={<StackView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

function renderStack() {
  return renderStackAt("/targets/M_42/stack");
}

afterEach(() => vi.restoreAllMocks());

describe("StackView", () => {
  it("renders simple fields from the schema and hides advanced behind a disclosure", async () => {
    mockSchema([
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
    mockSchema([]);
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
    mockSchema([]);
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
    mockSchema([]);
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
    mockSchema([]);
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

  it("warns at pick time about the borderline dark the finished run complains about", async () => {
    // A 30 s dark on 25 s subs. The engine's calibration_warnings reports it
    // (|25/30 − 1| = 0.167 > its 0.15 tolerance) — but the form's own, looser,
    // differently-anchored rule stayed silent, so the app went quiet before the
    // night was spent and complained afterwards. Both now use the engine's test,
    // served in `tolerances`.
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ dark_master_id: 1 });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 1, name: "Dark 30s", kind: "dark", filename: "d1.fits", n_frames: 20,
        method: "median", exposure_s: 30, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 25, gain: 80, sensor_temp_c: null },
      dark_master_id: 1, flat_master_id: null, flat_dark_master_id: null, bias_master_id: null,
      scores: { "1": 0.8 }, n_frames: 12,
      tolerances: { exposure_frac: 0.15, temp_c: 5 },
    });

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/shot at 30s but your subs are 25s/)).toBeInTheDocument());
  });

  it("warns when a chosen dark's temperature is far from the subs (even at a matched exposure)", async () => {
    mockSchema([]);
    // An exposure-matched (30 s) dark shot 15°C warmer than the subs — bias
    // scaling can't fix a temperature gap, so it warns regardless of exposure.
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ dark_master_id: 1 });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 1, name: "Dark 30s @20C", kind: "dark", filename: "d1.fits", n_frames: 20,
        method: "median", exposure_s: 30, gain: 80, sensor_temp_c: 20,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 30, gain: 80, sensor_temp_c: 5 },
      dark_master_id: 1, flat_master_id: null, flat_dark_master_id: null, bias_master_id: null,
      scores: { "1": 0.5 }, n_frames: 12,
    });

    renderStack();

    // No exposure warning (30 s matches 30 s), but the temperature gap warns.
    await waitFor(() =>
      expect(screen.getByText(/shot at 20°C but your subs are at 5°C/)).toBeInTheDocument());
    expect(screen.queryByText(/but your subs are 30s/)).not.toBeInTheDocument();
  });

  it("recommends the masters a walk-away stack would have used", async () => {
    // `recommend_masters` ranks a dark by *combined* distance, so an
    // exposure-perfect but gain-mismatched dark out-ranks the gain-matched one
    // the unattended binder would take. The form used to follow the first and
    // the walk-away path the second, so one target got calibrated two ways.
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 1, name: "Dark 30s gain 400", kind: "dark", filename: "d1.fits", n_frames: 20,
        method: "median", exposure_s: 30, gain: 400, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
      { id: 2, name: "Dark 120s gain 80", kind: "dark", filename: "d2.fits", n_frames: 20,
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
      dark_master_id: 1, flat_master_id: null, flat_dark_master_id: null, bias_master_id: 3,
      confident: { dark_master_id: 2, bias_master_id: 3, scale_dark_to_light: true },
      scores: { "1": 1, "2": 0.3, "3": 1 }, n_frames: 12,
    });

    renderStack();

    // The badge follows the confident pick, not the top-ranked one.
    await waitFor(() =>
      expect(screen.getByText(/Dark 120s gain 80.*★ recommended/)).toBeInTheDocument());
    expect(screen.queryByText(/Dark 30s gain 400.*★ recommended/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Use recommended"));

    // …and applying it brings the whole pairing: that dark is only usable here
    // *because* the bias scales it to the subs, so the switch comes with it.
    await waitFor(() =>
      expect(screen.getByText(/Dark exposure-scaling is on/)).toBeInTheDocument());
    expect(screen.queryByText(/shot at 120s but your subs are 30s/)).not.toBeInTheDocument();
    // Nothing left to apply.
    expect(screen.queryByText("Use recommended")).not.toBeInTheDocument();
  });

  it("keeps its best-available recommendation when nothing is confident", async () => {
    // A library whose only dark is a poor match still gets recommended, with the
    // existing caution doing the explaining — the form must not go blank just
    // because the unattended path would have declined.
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 2, name: "Dark 120s", kind: "dark", filename: "d2.fits", n_frames: 20,
        method: "median", exposure_s: 120, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 30, gain: 80, sensor_temp_c: null },
      dark_master_id: 2, flat_master_id: null, flat_dark_master_id: null, bias_master_id: null,
      confident: {},
      scores: { "2": 0.3 }, n_frames: 12,
    });

    renderStack();

    await waitFor(() => expect(screen.getByText("Use recommended")).toBeInTheDocument());
    expect(screen.getByText(/Dark 120s.*★ recommended/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Use recommended"));
    await waitFor(() =>
      expect(screen.getByText(/shot at 120s but your subs are 30s/)).toBeInTheDocument());
  });

  it("offers a one-click dark exposure-scaling when a bias is also selected, then confirms", async () => {
    mockSchema([]);
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

  it("refuses to promise a scale a wrong-sized bias can't deliver", async () => {
    mockSchema([]);
    // Scaling already on, a mismatched 120 s dark, and a bias from another
    // camera/binning. The engine needs the bias to be the dark's size to hold
    // the readout pedestal fixed, so it silently subtracts the dark *unscaled*.
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue(
      { dark_master_id: 2, bias_master_id: 3, scale_dark_to_light: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 2, name: "Dark 120s", kind: "dark", filename: "d2.fits", n_frames: 20,
        method: "median", exposure_s: 120, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
      { id: 3, name: "Bias (S30)", kind: "bias", filename: "b.fits", n_frames: 20,
        method: "median", exposure_s: 0, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 240, height_px: 160,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 30, gain: 80, sensor_temp_c: null,
                width_px: 480, height_px: 320 },
      dark_master_id: null, flat_master_id: null, flat_dark_master_id: null, bias_master_id: null,
      scores: {}, n_frames: 12,
    });

    renderStack();

    // Fail-before: the form said "Dark exposure-scaling is on — this 120s dark
    // will be scaled to match your 30s subs", which the stack does not do.
    await waitFor(() =>
      expect(screen.getByText(/scaling holds the bias pedestal fixed/)).toBeInTheDocument());
    expect(screen.getByText(/240×160 and the dark is 480×320/)).toBeInTheDocument();
    expect(screen.queryByText(/Dark exposure-scaling is on — this/)).not.toBeInTheDocument();
    // …so the plain exposure-mismatch warning is back, telling the truth.
    expect(screen.getByText(/shot at 120s but your subs are 30s/)).toBeInTheDocument();
    // …and the bias really is inert, which the existing note now says.
    expect(screen.getByText(/won't be subtracted from the lights again/))
      .toBeInTheDocument();
    // But NOT the generic "stacking will fail": with a dark chosen the engine
    // never validates the bias, so the stack runs — it just ignores it.
    expect(screen.queryByText(/Stacking with it\s+will fail/)).not.toBeInTheDocument();
  });

  it("proactively offers to select an available bias and scale the dark, then confirms", async () => {
    mockSchema([]);
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
    mockSchema([]);
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

  /** The Stack form with sigma clipping ticked, `n` accepted+solved subs, and the
   * engine's own `rejection_reach` answer for that stack — mocked per-request, so
   * clicking "Turn on Auto outlier removal" gets the answer the backend would
   * really give once the option is on (auto resolves to min/max down here). */
  function mockRejectionForm(n: number, reach: NonNullable<client.StackEstimate["rejection_reach"]>) {
    mockSchema([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: n }, (_, i) => mkFrame(i + 1)));
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockImplementation(async (_safe, opts) => ({
      n_frames: n, canvas_w: 480, canvas_h: 320, output_w: 480, output_h: 320,
      is_mosaic: false, peak_bytes: 7e6, peak_gb: 0.01,
      budget_bytes: 8e9, budget_gb: 8, would_exceed: false,
      suggested_drizzle_scale: null, suggested_reference_canvas: false, memory_fix: null,
      auto_reject_resolved: null,
      rejection_reach: opts.auto_reject && n >= 3
        ? { method: "min-max-reject" as const, n_frames: n,
            lone_outlier_min_frames: 3, reaches: true }
        : reach,
    }));
  }

  it("says a small default stack will combine as a plain average, with no rejection", async () => {
    // Three subs and sigma clipping ticked: the engine's dispatcher needs 4
    // frames, so nothing is rejected at all. The form used to call this
    // over-rejection and offer to turn the clip off — swapping no rejection for
    // no rejection — while `stackhealth` said the opposite on the finished picture.
    mockRejectionForm(3, {
      method: "mean", n_frames: 3, lone_outlier_min_frames: null, reaches: false,
    });

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/will combine as a plain average/)).toBeInTheDocument());
    expect(screen.queryByText(/it can reject real signal as an outlier/))
      .not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Turn off sigma clipping" }))
      .not.toBeInTheDocument();
  });

  it("warns that sigma clipping is blind to a lone trail below the κ threshold", async () => {
    mockRejectionForm(6, {
      method: "sigma-clip", n_frames: 6, lone_outlier_min_frames: 11, reaches: false,
    });

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/can't actually drop a passing/)).toBeInTheDocument());
    expect(screen.getByText(/about 11 frames up/)).toBeInTheDocument();
  });

  it("turns on Auto outlier removal in one click from the caution, then hides it", async () => {
    mockRejectionForm(6, {
      method: "sigma-clip", n_frames: 6, lone_outlier_min_frames: 11, reaches: false,
    });

    renderStack();

    const btn = await screen.findByRole("button", { name: "Turn on Auto outlier removal" });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.queryByText(/can't actually drop a passing/)).not.toBeInTheDocument());
  });

  it("says nothing once the rejection can actually reach a lone outlier", async () => {
    mockRejectionForm(20, {
      method: "sigma-clip", n_frames: 20, lone_outlier_min_frames: 11, reaches: true,
    });

    renderStack();

    await waitFor(() => expect(screen.getByText("Sigma clipping")).toBeInTheDocument());
    expect(screen.queryByText(/can't actually drop a passing/)).not.toBeInTheDocument();
    expect(screen.queryByText(/will combine as a plain average/)).not.toBeInTheDocument();
    expect(screen.queryByText(/it can reject real signal as an outlier/))
      .not.toBeInTheDocument();
  });

  it("warns when the accepted+solved subs look like two different targets", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    // Two well-separated pointings (RA 10 vs RA 83) in one folder.
    const frames = [
      ...Array.from({ length: 16 }, (_, i) => ({
        ...mkFrame(i + 1), ra_center_deg: 10 + (i % 3) * 0.2, dec_center_deg: 20,
      })),
      ...Array.from({ length: 12 }, (_, i) => ({
        ...mkFrame(i + 100), ra_center_deg: 83 + (i % 3) * 0.2, dec_center_deg: -5,
      })),
    ];
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    expect(
      await screen.findByText("This batch looks like 2 different targets"),
    ).toBeInTheDocument();
  });

  it("does not warn about mixed targets for a single pointing", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    const frames = Array.from({ length: 20 }, (_, i) => ({
      ...mkFrame(i + 1), ra_center_deg: 10 + (i % 3) * 0.2, dec_center_deg: 20,
    }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() => expect(screen.getByText("Start stacking")).toBeInTheDocument());
    expect(
      screen.queryByText(/looks like .* different targets/),
    ).not.toBeInTheDocument();
  });

  it("hints to tighten kappa on a very large stack", async () => {
    mockSchema([
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
    mockSchema([
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

  it("tightens kappa in one click from the large-stack hint, then hides it", async () => {
    mockSchema([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "sigma_kappa", label: "Sigma κ", type: "float", group: "simple",
        default: 3, min: 1, max: 5, step: 0.1, options: null, help: null, depends_on: "sigma_clip" },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true, sigma_kappa: 3 });
    const frames = Array.from({ length: 250 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    const btn = await screen.findByRole("button", { name: "Tighten κ to 2.5" });
    fireEvent.click(btn);
    // Once κ is at 2.5 (< 3) the hint no longer applies and disappears.
    await waitFor(() =>
      expect(screen.queryByText(/tighter sigma-clip/)).not.toBeInTheDocument());
  });

  it("turns on sigma clipping in one click from the streak-no-rejection warning", async () => {
    mockSchema([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: false });
    // ≥11 frames so the generic "turn on sigma clipping" advice (not the min/max
    // hint) is the right one, with one streaked frame and no rejection on.
    const frames = Array.from({ length: 12 }, (_, i) =>
      ({ ...mkFrame(i + 1), streak_detected: i === 0 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    const btn = await screen.findByRole("button", { name: "Turn on sigma clipping" });
    fireEvent.click(btn);
    // With sigma clipping on the stack now has per-pixel rejection → warning hides.
    await waitFor(() =>
      expect(screen.queryByText(/detected satellite\/plane streak/)).not.toBeInTheDocument());
  });

  it("turns on drizzle outlier rejection in one click from the drizzle+sigma-clip hint", async () => {
    mockSchema([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "drizzle", label: "Drizzle", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "drizzle_reject", label: "Drizzle outlier rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: "drizzle" },
    ]);
    // drizzle + sigma_clip on, drizzle_reject off → the mismatch hint fires.
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({
      sigma_clip: true, drizzle: true, drizzle_reject: false,
    });
    const frames = Array.from({ length: 8 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    const btn = await screen.findByRole("button", { name: "Turn on drizzle outlier rejection" });
    fireEvent.click(btn);
    // Enabling drizzle rejection resolves the mismatch → the hint disappears.
    await waitFor(() =>
      expect(screen.queryByText(/Sigma clipping doesn't apply to drizzle/)).not.toBeInTheDocument());
  });

  it("warns when accepted streaked frames are stacked without rejection", async () => {
    mockSchema([
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
    mockSchema([
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
    mockSchema([
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
    mockSchema([
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
    mockSchema([
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

  it("warns that min/max rejection ignores quality weighting when both are on", async () => {
    mockSchema([
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "quality_weighted", label: "Quality weighting", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    // Both min/max reject and quality weighting on, ≥3 frames, non-drizzle path:
    // the engine stamps weights_applied=False here, so the weighting is a no-op.
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue(
      { min_max_reject: true, quality_weighted: true });
    const frames = Array.from({ length: 6 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/Min\/max rejection and quality weighting don't combine/))
        .toBeInTheDocument());
  });

  it("clears the min/max+weighting warning in one click by turning weighting off", async () => {
    mockSchema([
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "quality_weighted", label: "Quality weighting", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue(
      { min_max_reject: true, quality_weighted: true });
    const frames = Array.from({ length: 6 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    const btn = await screen.findByRole("button", { name: "Turn off quality weighting" });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.queryByText(/don't combine/)).not.toBeInTheDocument());
  });

  it("does not warn about min/max+weighting when only min/max reject is on", async () => {
    mockSchema([
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "quality_weighted", label: "Quality weighting", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue(
      { min_max_reject: true, quality_weighted: false });
    const frames = Array.from({ length: 6 }, (_, i) => mkFrame(i + 1));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    const toggle = await screen.findByLabelText("Min/max rejection");
    await waitFor(() => expect(toggle).toBeChecked());
    expect(screen.queryByText(/don't combine/)).not.toBeInTheDocument();
  });

  it("warns when the min/max reject k is too high for the frame count", async () => {
    mockSchema([
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
    mockSchema([
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
    mockSchema([
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
    mockSchema([
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
    mockSchema([
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
    mockSchema([
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
    mockSchema([
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
    mockSchema(drizzleSchema);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue(
      { sigma_clip: true, drizzle: true, drizzle_reject: false });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/doesn't apply to drizzle's single-pass/)).toBeInTheDocument());
  });

  it("drops the drizzle hint once outlier rejection is enabled", async () => {
    mockSchema(drizzleSchema);
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
    mockSchema([]);
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
    mockSchema([]);
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
    mockSchema([]);
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
    mockSchema([]);
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
    mockSchema([]);
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
    mockSchema([]);
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
    mockSchema([]);
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
    mockSchema([]);
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
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ photometric_normalize: true });
    const frames = Array.from({ length: 8 }, (_, i) =>
      ({ ...mkFrame(i + 1), transparency_score: 2000 + i * 1000 }));
    vi.spyOn(client.api, "listFrames").mockResolvedValue(frames);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);

    renderStack();

    await waitFor(() => expect(screen.getByText("Start stacking")).toBeInTheDocument());
    expect(screen.queryByText(/vary a lot in transparency/)).not.toBeInTheDocument();
  });

  it("still renders the form (never hangs the loader) when the reuse fetch errors", async () => {
    // The form body is gated on the values being seeded from defaults (so
    // data-driven nudges don't flash against the empty initial state). The seed
    // effect must therefore settle even when the ?from= reuse fetch *errors* —
    // otherwise it would return forever and hang the page on the spinner.
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackRunOptions").mockRejectedValue(new Error("run gone"));

    renderStackAt("/targets/M_42/stack?from=5");

    // Falls through to the defaults-seeded form instead of hanging.
    await waitFor(() => expect(screen.getByText("Start stacking")).toBeInTheDocument());
  });

  it("hints to review auto-grade when accepted frames look like outliers", async () => {
    mockSchema([]);
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
    mockSchema([]);
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
    mockSchema([]);
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
    mockSchema([]);
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
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue({
      n_frames: 2, canvas_w: 480, canvas_h: 320, output_w: 480, output_h: 320,
      is_mosaic: false, peak_bytes: 7e6, peak_gb: 0.01,
      budget_bytes: 8e9, budget_gb: 8, would_exceed: false,
      suggested_drizzle_scale: null, suggested_reference_canvas: false, memory_fix: null,
      auto_reject_resolved: null,
    });

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/2 accepted, solved frames · output 480×320/)).toBeInTheDocument());
    expect(screen.getByText(/GB peak memory/)).toBeInTheDocument();
  });

  // The print line — the canvas said in a unit a human has an intuition for,
  // while the knob that fixes it is still on screen.
  const PRINT_PLAN = {
    name: "A4", dpi: 210, text: "This stack would print sharply up to A4.",
    bigger_name: "A3", bigger_drizzle_scale: 1.4,
    bigger_text: "Raising Drizzle to ×1.4 would print it at A3 instead — "
      + "super-resolution needs plenty of well-dithered subs to pay off.",
  };

  function printEstimate(
    over: boolean, nFrames: number,
    plan: client.StackEstimate["print_plan"] = PRINT_PLAN,
  ): client.StackEstimate {
    return {
      n_frames: nFrames, canvas_w: 3000, canvas_h: 2000,
      output_w: 3000, output_h: 2000, is_mosaic: false,
      peak_bytes: 2.3e9, peak_gb: 2.3,
      budget_bytes: over ? 1.4e9 : 8e9, budget_gb: over ? 1.4 : 8,
      would_exceed: over,
      suggested_drizzle_scale: null, suggested_reference_canvas: false,
      memory_fix: null, auto_reject_resolved: null, print_plan: plan,
    };
  }

  function mockPrintForm(est: client.StackEstimate) {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue(est);
  }

  it("says what the stack would print at, and the drizzle scale that prints bigger", async () => {
    mockPrintForm(printEstimate(false, 250));
    renderStack();
    await waitFor(() =>
      expect(screen.getByText(/print sharply up to A4/)).toBeInTheDocument());
    expect(screen.getByText(/Raising Drizzle to ×1.4 would print it at A3/))
      .toBeInTheDocument();
  });

  it("offers the bigger print as a button, not only a sentence, and one click "
    + "sets both drizzle knobs at once", async () => {
    // The scale the sentence names is already verified to reach that paper and
    // to fit the memory budget — but both knobs it names live inside the
    // collapsed advanced disclosure, so reading it left a beginner hunting.
    mockPrintForm(printEstimate(false, 250));
    const estimate = vi.spyOn(client.api, "stackEstimate");
    renderStack();

    const button = await screen.findByRole("button",
      { name: "Use drizzle ×1.4 — prints at A3" });
    estimate.mockClear();
    fireEvent.click(button);

    // Both keys land in one update: the estimate is keyed on each, so a
    // two-step set would re-query through "drizzle on at the old scale".
    await waitFor(() => expect(estimate).toHaveBeenCalled());
    for (const call of estimate.mock.calls) {
      expect(call[1]).toMatchObject({ drizzle: true, drizzle_scale: 1.4 });
    }
  });

  it("withholds the bigger-print button wherever it withholds the sentence",
    async () => {
      // It is gated on the sentence, so it inherits every condition that
      // sentence is held to and can never appear on its own.
      mockPrintForm(printEstimate(false, 12));
      renderStack();
      await waitFor(() =>
        expect(screen.getByText(/print sharply up to A4/)).toBeInTheDocument());
      expect(screen.queryByRole("button", { name: /prints at A3/ }))
        .not.toBeInTheDocument();
    });

  it("withholds the bigger-print nudge on a stack with too few frames for drizzle", async () => {
    // The form already warns that drizzle needs 200+ dithered subs; recommending
    // it a line above that warning would be the panel arguing with itself.
    mockPrintForm(printEstimate(false, 12));
    renderStack();
    await waitFor(() =>
      expect(screen.getByText(/print sharply up to A4/)).toBeInTheDocument());
    expect(screen.queryByText(/Raising Drizzle/)).not.toBeInTheDocument();
  });

  it("says nothing about printing when the run is over budget", async () => {
    // The over-budget alert replaces the sizing line entirely — a print nudge
    // beside a refusal is two answers to one question.
    mockPrintForm(printEstimate(true, 250));
    renderStack();
    await waitFor(() =>
      expect(screen.getByText(/over the ~1.4 GB budget/)).toBeInTheDocument());
    expect(screen.queryByText(/print sharply up to A4/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Raising Drizzle/)).not.toBeInTheDocument();
  });

  it("degrades quietly when the backend sends no print plan", async () => {
    mockPrintForm(printEstimate(false, 250, null));
    renderStack();
    // The sizing line itself — `est.n_frames`, i.e. the 250 this estimate is for.
    // (It used to match "2 accepted, solved frames", which was the *sigma-clip*
    // caution counting the two mocked frames, not the sizing line at all.)
    await waitFor(() =>
      expect(screen.getByText(/250 accepted, solved frames · output 3000×2000/))
        .toBeInTheDocument());
    expect(screen.queryByText(/print sharply/)).not.toBeInTheDocument();
  });

  it("warns in red when the estimate exceeds the memory budget", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue({
      n_frames: 2, canvas_w: 8000, canvas_h: 6000, output_w: 16000, output_h: 12000,
      is_mosaic: true, peak_bytes: 5.4e9, peak_gb: 5.4,
      budget_bytes: 1.4e9, budget_gb: 1.4, would_exceed: true,
      suggested_drizzle_scale: null, suggested_reference_canvas: false, memory_fix: null,
      auto_reject_resolved: null,
    });

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/over the ~1.4 GB budget/)).toBeInTheDocument());
  });

  it("offers a one-click smaller drizzle scale when one fits the budget", async () => {
    mockSchema([]);
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
      memory_fix: { kind: "drizzle_scale", value: 1.4, peak_bytes: 1.3e9, peak_gb: 1.3 },
      auto_reject_resolved: null,
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
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue({
      n_frames: 2, canvas_w: 8000, canvas_h: 6000, output_w: 8000, output_h: 6000,
      is_mosaic: true, peak_bytes: 2.3e9, peak_gb: 2.3,
      budget_bytes: 1.4e9, budget_gb: 1.4, would_exceed: true,
      suggested_drizzle_scale: null, suggested_reference_canvas: true,
      memory_fix: { kind: "reference_canvas", value: null, peak_bytes: 1.2e9, peak_gb: 1.2 },
      auto_reject_resolved: null,
    });

    renderStack();

    const btn = await screen.findByRole("button", { name: /Use the reference canvas instead/ });
    fireEvent.click(btn);
    // Clicking switches mosaic_canvas → reference so the next estimate re-queries.
    await waitFor(() =>
      expect(client.api.stackEstimate).toHaveBeenCalledWith(
        "M_42", expect.objectContaining({ mosaic_canvas: "reference" })));
  });

  it("offers dropping extra outlier passes — the least-destructive lever — with its peak", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({
      min_max_reject: true, min_max_reject_count: 3,
    });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1), mkFrame(2)]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue({
      n_frames: 2, canvas_w: 4000, canvas_h: 4000, output_w: 4000, output_h: 4000,
      is_mosaic: true, peak_bytes: 1.5e9, peak_gb: 1.5,
      budget_bytes: 1e9, budget_gb: 1, would_exceed: true,
      // A k>1 reject is the only reason it busts the budget → dropping the extra
      // passes (a smaller change than cropping the canvas) is offered first.
      suggested_drizzle_scale: null, suggested_reference_canvas: false,
      memory_fix: { kind: "reduce_outlier_passes", value: null, peak_bytes: 0.77e9, peak_gb: 0.77 },
      auto_reject_resolved: null,
    });

    renderStack();

    const btn = await screen.findByRole("button", {
      name: /Lower Extra outlier passes to 1 — fits at ~0.77 GB/,
    });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(client.api.stackEstimate).toHaveBeenCalledWith(
        "M_42", expect.objectContaining({ min_max_reject_count: 1 })));
  });

  // A dry-run estimate the drizzle-on feasibility check resolves to. `is_mosaic`
  // / `would_exceed` are what the nudge gates on.
  function estimateResult(over: boolean, mosaic: boolean): client.StackEstimate {
    return {
      n_frames: 250, canvas_w: 480, canvas_h: 320, output_w: 720, output_h: 480,
      is_mosaic: mosaic, peak_bytes: over ? 5.4e9 : 3e8, peak_gb: over ? 5.4 : 0.3,
      budget_bytes: 1.4e9, budget_gb: 1.4, would_exceed: over,
      suggested_drizzle_scale: null, suggested_reference_canvas: false, memory_fix: null,
      auto_reject_resolved: null,
    };
  }

  function rejectFields(): client.StackOptionField[] {
    return [
      { key: "auto_reject", label: "Auto outlier removal", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null, depends_on: null },
      { key: "min_max_reject", label: "Min/max rejection", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ];
  }

  it("says which method Auto outlier removal will actually use, and greys the toggles it overrides", async () => {
    // The form used to show "Sigma clipping: ON" while a 6-frame stack really
    // ran min/max — the displayed state could be the exact opposite of what
    // happened, and the beginner only found out from the History badge.
    mockSchema(rejectFields());
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({
      auto_reject: true, sigma_clip: true, min_max_reject: false });
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 6 }, (_, i) => mkFrame(i + 1)));
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue({
      ...estimateResult(false, false),
      n_frames: 6,
      auto_reject_resolved: { method: "min_max", switch_at_frames: 11, n_frames: 6 },
    });

    renderStack();

    // The truth, in the user's own numbers, not a generic "auto decides".
    await waitFor(() => expect(
      screen.getByText(/with 6 accepted, solved subs it will use min\/max rejection/),
    ).toBeInTheDocument());
    expect(screen.getByText(/switches to sigma clipping from about 11 subs/))
      .toBeInTheDocument();
    // …and the two switches Auto overrides no longer read as live controls.
    expect(screen.getByRole("switch", { name: "Sigma clipping" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "Min/max rejection" })).toBeDisabled();
    // Auto itself stays live — turning it off is how you take the wheel back.
    expect(screen.getByRole("switch", { name: "Auto outlier removal" }))
      .not.toBeDisabled();
  });

  it("leaves the rejection toggles live when Auto outlier removal is off", async () => {
    mockSchema(rejectFields());
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({
      auto_reject: false, sigma_clip: true, min_max_reject: false });
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 6 }, (_, i) => mkFrame(i + 1)));
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue({
      ...estimateResult(false, false), n_frames: 6, auto_reject_resolved: null });

    renderStack();

    await waitFor(() => expect(
      screen.getByRole("switch", { name: "Sigma clipping" })).not.toBeDisabled());
    expect(screen.getByRole("switch", { name: "Min/max rejection" }))
      .not.toBeDisabled();
    expect(screen.queryByText(/Auto outlier removal is on/)).not.toBeInTheDocument();
  });

  it("nudges Drizzle on a large single-field set that fits the budget", async () => {
    mockSchema([
      { key: "drizzle", label: "Drizzle", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ drizzle: false });
    // 250 accepted, solved frames — above the 200-frame drizzle threshold.
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 250 }, (_, i) => mkFrame(i + 1)));
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue(estimateResult(false, false));

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/exactly where Drizzle pays off/)).toBeInTheDocument());
  });

  it("does not nudge Drizzle on a small set", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ drizzle: false });
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 50 }, (_, i) => mkFrame(i + 1)));
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue(estimateResult(false, false));

    renderStack();

    // Form ready; a 50-frame stack is below the threshold so the feasibility
    // query never even fires and the nudge stays absent.
    await screen.findByRole("button", { name: "Start stacking" });
    expect(screen.queryByText(/exactly where Drizzle pays off/)).not.toBeInTheDocument();
  });

  it("does not nudge Drizzle when a drizzled run would exceed the memory budget", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ drizzle: false });
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 250 }, (_, i) => mkFrame(i + 1)));
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    // Base estimate fits; the drizzle-on feasibility estimate blows the budget.
    vi.spyOn(client.api, "stackEstimate").mockImplementation((_safe, opts) =>
      Promise.resolve(opts?.drizzle ? estimateResult(true, false) : estimateResult(false, false)));

    renderStack();

    await screen.findByRole("button", { name: "Start stacking" });
    // The drizzle-on feasibility estimate resolves over-budget, so despite the
    // large set the nudge is suppressed.
    await waitFor(() => expect(client.api.stackEstimate).toHaveBeenCalledWith(
      "M_42", expect.objectContaining({ drizzle: true })));
    expect(screen.queryByText(/exactly where Drizzle pays off/)).not.toBeInTheDocument();
  });

  it("does not nudge Drizzle on a mosaic canvas", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ drizzle: false });
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 250 }, (_, i) => mkFrame(i + 1)));
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue(estimateResult(false, true));

    renderStack();

    await screen.findByRole("button", { name: "Start stacking" });
    await waitFor(() => expect(client.api.stackEstimate).toHaveBeenCalledWith(
      "M_42", expect.objectContaining({ drizzle: true })));
    expect(screen.queryByText(/exactly where Drizzle pays off/)).not.toBeInTheDocument();
  });

  it("turns on Drizzle in one click from the nudge, then hides it", async () => {
    mockSchema([
      { key: "drizzle", label: "Drizzle", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ drizzle: false });
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 250 }, (_, i) => mkFrame(i + 1)));
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue(estimateResult(false, false));

    renderStack();

    const btn = await screen.findByRole("button", { name: "Turn on Drizzle" });
    fireEvent.click(btn);
    // With drizzle now on the nudge no longer applies and disappears.
    await waitFor(() =>
      expect(screen.queryByText(/exactly where Drizzle pays off/)).not.toBeInTheDocument());
  });

  it("cautions when Drizzle is on but too few frames are accepted", async () => {
    mockSchema([
      { key: "drizzle", label: "Drizzle", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ drizzle: true });
    // 30 accepted, solved frames — well under the 100-frame drizzle floor.
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 30 }, (_, i) => mkFrame(i + 1)));
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue(estimateResult(false, false));

    renderStack();

    await waitFor(() =>
      expect(screen.getByText(/needs lots of dithered frames/)).toBeInTheDocument());
  });

  it("does not caution Drizzle on a large set", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ drizzle: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 250 }, (_, i) => mkFrame(i + 1)));
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue(estimateResult(false, false));

    renderStack();

    await screen.findByRole("button", { name: "Start stacking" });
    expect(screen.queryByText(/needs lots of dithered frames/)).not.toBeInTheDocument();
  });

  it("does not caution Drizzle when it is off", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ drizzle: false });
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 30 }, (_, i) => mkFrame(i + 1)));
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue(estimateResult(false, false));

    renderStack();

    await screen.findByRole("button", { name: "Start stacking" });
    expect(screen.queryByText(/needs lots of dithered frames/)).not.toBeInTheDocument();
  });

  it("turns off Drizzle in one click from the too-few-frames caution, then hides it", async () => {
    mockSchema([
      { key: "drizzle", label: "Drizzle", type: "bool", group: "simple",
        default: false, min: null, max: null, step: null, options: null, help: null, depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ drizzle: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue(
      Array.from({ length: 30 }, (_, i) => mkFrame(i + 1)));
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "stackEstimate").mockResolvedValue(estimateResult(false, false));

    renderStack();

    const btn = await screen.findByRole("button", { name: "Turn off Drizzle" });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.queryByText(/needs lots of dithered frames/)).not.toBeInTheDocument());
  });

  it("titles the page with the target's friendly name, not the URL slug", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      { safe: "NGC_7000", name: "NGC 7000" } as never);

    renderStackAt("/targets/NGC_7000/stack");

    await waitFor(() =>
      expect(screen.getByText("Stack — NGC 7000")).toBeInTheDocument());
    expect(screen.queryByText("Stack — NGC_7000")).not.toBeInTheDocument();
  });

  it("flags a wrong-camera master at pick time instead of failing the stack", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ dark_master_id: 9 });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 9, name: "S50 Dark", kind: "dark", filename: "d9.fits", n_frames: 20,
        method: "median", exposure_s: 30, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 1080, height_px: 1920,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 30, gain: 80, sensor_temp_c: null,
                width_px: 480, height_px: 320 },
      dark_master_id: null, flat_master_id: null, flat_dark_master_id: null,
      bias_master_id: null, scores: {}, n_frames: 12,
    });

    renderStack();

    // The chosen dark is 1080x1920 but the subs are 480x320 — the engine would
    // refuse it and the whole stack would die, so it's called out up front.
    await waitFor(() =>
      expect(screen.getByText(/different camera or binning mode/)).toBeInTheDocument());
    // …and the picker itself marks it, so it reads as unusable before it's chosen.
    expect(screen.getByText(/S50 Dark.*wrong size for this target/)).toBeInTheDocument();
  });

  it("stays quiet when the master matches the target's frames", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ dark_master_id: 9 });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      { id: 9, name: "Matching Dark", kind: "dark", filename: "d9.fits", n_frames: 20,
        method: "median", exposure_s: 30, gain: 80, sensor_temp_c: null,
        bayer_pattern: "RGGB", width_px: 480, height_px: 320,
        created_utc: "2026-01-01T00:00:00", exists: true },
    ]);
    vi.spyOn(client.api, "calibrationSuggestions").mockResolvedValue({
      params: { exposure_s: 30, gain: 80, sensor_temp_c: null,
                width_px: 480, height_px: 320 },
      dark_master_id: 9, flat_master_id: null, flat_dark_master_id: null,
      bias_master_id: null, scores: { "9": 1 }, n_frames: 12,
    });

    renderStack();

    await waitFor(() => expect(screen.getByText("Start stacking")).toBeInTheDocument());
    expect(screen.queryByText(/different camera or binning mode/)).not.toBeInTheDocument();
    expect(screen.queryByText(/wrong size for this target/)).not.toBeInTheDocument();
  });

  // --- background-mode nudge (big emission nebula → Luminance) --------------

  const bgSchema = [
    { key: "background_flatten", label: "Background flatten", type: "bool", group: "simple",
      default: true, min: null, max: null, step: null, options: null, help: null,
      depends_on: null },
    { key: "background_mode", label: "Background mode", type: "enum", group: "advanced",
      default: "per_channel", min: null, max: null, step: null,
      options: ["per_channel", "luminance"],
      option_labels: { per_channel: "Per channel", luminance: "Luminance" },
      help: null, depends_on: "background_flatten" },
  ] as client.StackOptionField[];

  const orion = (over: Partial<client.ObjectInfo> = {}): client.ObjectInfo => ({
    id: "M42", name: "Orion Nebula", type: "nebula", constellation: "Orion",
    constellation_abbr: "Ori", ra_deg: 83.8, dec_deg: -5.4, matched_by: "name",
    size_arcmin: 85,
    background_mode_hint: {
      mode: "luminance",
      text: "This target is a large patch of glowing gas … cyan cores and red halos …",
    },
    ...over,
  });

  function mockBgForm(info: client.ObjectInfo | null,
                      defaults: Record<string, unknown> = {
                        background_flatten: true, background_mode: "per_channel",
                      }) {
    mockSchema(bgSchema);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue(defaults);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    vi.spyOn(client.api, "identifyTarget").mockResolvedValue(info);
  }

  it("nudges a big emission nebula toward Luminance background flatten", async () => {
    mockBgForm(orion());
    renderStack();
    await waitFor(() =>
      expect(screen.getByText(/cyan cores and red halos/)).toBeInTheDocument());
    // The button names the mode using the engine's own option label.
    expect(screen.getByRole("button", { name: "Use Luminance background flatten" }))
      .toBeInTheDocument();
  });

  it("switches to the advised mode in one click, then hides the nudge", async () => {
    mockBgForm(orion());
    renderStack();
    const btn = await screen.findByRole(
      "button", { name: "Use Luminance background flatten" });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(screen.queryByText(/cyan cores and red halos/)).not.toBeInTheDocument());
  });

  it("says nothing for a target the catalog doesn't flag", async () => {
    // A galaxy carries no advice — the per-channel default is right for it.
    mockBgForm(orion({ type: "galaxy", background_mode_hint: null }));
    renderStack();
    await waitFor(() => expect(screen.getByText("Start stacking")).toBeInTheDocument());
    expect(screen.queryByText(/cyan cores and red halos/)).not.toBeInTheDocument();
  });

  it("says nothing when the per-frame flatten is switched off", async () => {
    mockBgForm(orion(), { background_flatten: false, background_mode: "per_channel" });
    renderStack();
    await waitFor(() => expect(screen.getByText("Start stacking")).toBeInTheDocument());
    expect(screen.queryByText(/cyan cores and red halos/)).not.toBeInTheDocument();
  });

  it("falls back to the slug in the title when the target record can't be loaded", async () => {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "getTarget").mockRejectedValue(new Error("404"));

    renderStackAt("/targets/M_42/stack");

    await waitFor(() =>
      expect(screen.getByText("Stack — M_42")).toBeInTheDocument());
  });
});

// A stack that fails is the one moment on this page where a beginner most needs
// a sentence they can act on, and it was the one place in the app that printed
// the engine's raw exception instead — `Error: MemoryError: stack output canvas
// needs ~9.4 GB of working memory, over the ~6.0 GB budget`. Every other surface
// that shows a failed job (the Jobs page, `StackFailedAlert`) runs it through
// `friendlyJobError` first.
describe("StackView — a stack that fails says so in plain language", () => {
  /** Minimal EventSource stand-in, so a test can push a job snapshot at the
   *  page the way the server's SSE stream does. Mirrors the one in
   *  `hooks/useJobEvents.test.ts`. */
  class MockEventSource {
    static instances: MockEventSource[] = [];
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSED = 2;
    url: string;
    readyState = MockEventSource.CONNECTING;
    listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
    onerror: (() => void) | null = null;
    constructor(url: string) {
      this.url = url;
      MockEventSource.instances.push(this);
    }
    addEventListener(type: string, cb: (e: MessageEvent) => void) {
      (this.listeners[type] ??= []).push(cb);
    }
    emit(type: string, data: unknown) {
      (this.listeners[type] ?? []).forEach(
        (cb) => cb({ data: JSON.stringify(data) } as MessageEvent));
    }
    close() { this.readyState = MockEventSource.CLOSED; }
  }

  afterEach(() => {
    MockEventSource.instances = [];
    vi.unstubAllGlobals();
  });

  /** One accepted, plate-solved sub — without it "Start stacking" is disabled. */
  function solvedFrame(): client.Frame {
    return {
      id: 1, name: "f1.fits", timestamp_utc: null, exposure_s: 30, gain: 80,
      width_px: 480, height_px: 320, bayer_pattern: "RGGB", solved: true,
      ra_center_deg: null, dec_center_deg: null, ra_hint_deg: null,
      dec_hint_deg: null, fwhm_px: null, star_count: null, sky_adu_median: null,
      eccentricity_median: null, transparency_score: null,
      streak_detected: false, accept: true, reject_reason: null,
      user_override: false,
    };
  }

  function mockStartableForm() {
    mockSchema([]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({});
    vi.spyOn(client.api, "listFrames").mockResolvedValue([solvedFrame()]);
    vi.spyOn(client.api, "triggerStack").mockResolvedValue({ job_id: "j1" });
    vi.stubGlobal("EventSource", MockEventSource);
  }

  /** Start a stack on a rendered page and push one failed-job snapshot. */
  async function failWith(error: string, kind?: string | null) {
    mockStartableForm();

    renderStack();
    fireEvent.click(await screen.findByRole("button", { name: "Start stacking" }));
    await waitFor(() => expect(MockEventSource.instances.length).toBe(1));
    act(() => {
      MockEventSource.instances[0].emit("progress", {
        id: "j1", kind: "stack", state: "error", phase: "", done: 0, total: 1,
        detail: "", created_utc: null, started_utc: null, finished_utc: null,
        error, error_kind: kind ?? null, result: null,
      });
    });
    return screen.findByTestId("stack-job-error");
  }

  it("translates the failure and keeps the engine's numbers underneath", async () => {
    const alert = await failWith(
      "MemoryError: stack output canvas needs ~9.4 GB of working memory, "
      + "over the ~6.0 GB budget", "memory_budget");

    // The plain-language sentence the Jobs page already writes for this kind…
    expect(alert.textContent).toMatch(/memory/i);
    expect(alert.textContent).not.toMatch(/^Error: /);
    // …the engine's own line, kept because only it carries the numbers…
    expect(alert.textContent).toContain("~9.4 GB");
    // …and the raw exception is no longer the *status* line.
    expect(screen.queryByText(/^Error: MemoryError/)).not.toBeInTheDocument();
    expect(screen.getByText("Stack didn't finish")).toBeInTheDocument();
  });

  it("does not print an unrecognised error twice", async () => {
    // `friendlyJobError` returns an unrecognised error *as* its own message, so
    // the raw line underneath would be the same sentence over again.
    const alert = await failWith("OSError: disk is full");
    const hits = alert.textContent?.match(/disk is full/g) ?? [];
    expect(hits.length).toBe(1);
  });

  it("shows nothing extra while a stack is merely running", async () => {
    mockStartableForm();

    renderStack();
    fireEvent.click(await screen.findByRole("button", { name: "Start stacking" }));
    await waitFor(() => expect(MockEventSource.instances.length).toBe(1));
    act(() => {
      MockEventSource.instances[0].emit("progress", {
        id: "j1", kind: "stack", state: "running", phase: "aligning", done: 3,
        total: 10, detail: "", created_utc: null, started_utc: null,
        finished_utc: null, error: null, error_kind: null, result: null,
      });
    });

    await screen.findByText("aligning 3/10");
    expect(screen.queryByTestId("stack-job-error")).not.toBeInTheDocument();
  });
});

// Saving is the moment the decision is made, and until now it was the one place
// the app never answered "will this actually remove a satellite trail?". The
// form's own caution speaks for the run you are about to trigger; the Target
// page's note is gated on a trail already having been flagged. A saved default
// drives every *unattended* stack from then on, so the confirmation says what it
// will do there — with the Auto toggle still on screen.
describe("StackView — what a saved default will do overnight", () => {
  /** The Stack form with one saveable option, `n` accepted+solved subs, and the
   *  server's `/rejection-outlook` answer for whatever ends up stored. */
  function mockSaveForm(outlook: client.RejectionOutlook | null) {
    mockSchema([
      { key: "sigma_clip", label: "Sigma clipping", type: "bool", group: "simple",
        default: true, min: null, max: null, step: null, options: null, help: null,
        depends_on: null },
    ]);
    vi.spyOn(client.api, "getStackDefaults").mockResolvedValue({ sigma_clip: true });
    vi.spyOn(client.api, "listFrames").mockResolvedValue([]);
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([]);
    const put = vi.spyOn(client.api, "putStackDefaults")
      .mockResolvedValue({ sigma_clip: true });
    const ask = outlook === null
      ? vi.spyOn(client.api, "rejectionOutlook").mockRejectedValue(new Error("nope"))
      : vi.spyOn(client.api, "rejectionOutlook").mockResolvedValue(outlook);
    return { put, ask };
  }

  const blind: client.RejectionOutlook = {
    method: "sigma-clip", n_frames: 6, panel_depth: null,
    lone_outlier_min_frames: 11, reaches: false, user_chose: true,
  };

  it("warns, on the save, that the saved rejection is blind overnight", async () => {
    const show = vi.spyOn(notifications, "show").mockImplementation(() => "");
    const { put, ask } = mockSaveForm(blind);

    renderStack();
    fireEvent.click(await screen.findByRole("button", { name: "Save as defaults" }));

    await waitFor(() => expect(show).toHaveBeenCalled());
    const shown = show.mock.calls[show.mock.calls.length - 1][0] as
      { message: string; color: string };
    // The save itself still succeeded, and still says so.
    expect(put).toHaveBeenCalled();
    expect(shown.message).toContain("will pre-fill this form");
    expect(shown.message).toContain("overnight and one-click stacks");
    expect(shown.message).toContain("Auto outlier removal");
    expect(shown.color).toBe("yellow");
    // Asked of the *stored* blob, not the values on screen.
    expect(ask).toHaveBeenCalledWith("M_42");
  });

  it("says only the plain confirmation when the saved rejection does reach", async () => {
    const show = vi.spyOn(notifications, "show").mockImplementation(() => "");
    mockSaveForm({ ...blind, reaches: true });

    renderStack();
    fireEvent.click(await screen.findByRole("button", { name: "Save as defaults" }));

    await waitFor(() => expect(show).toHaveBeenCalled());
    const shown = show.mock.calls[show.mock.calls.length - 1][0] as
      { message: string; color: string };
    expect(shown.message).toContain("will pre-fill this form");
    expect(shown.message).not.toContain("Heads-up");
    expect(shown.color).toBe("teal");
  });

  it("still confirms the save when the outlook can't be had", async () => {
    // An older backend, or nothing solved yet: the save worked, so it must not
    // read as a failure just because the extra question went unanswered.
    const show = vi.spyOn(notifications, "show").mockImplementation(() => "");
    const { put } = mockSaveForm(null);

    renderStack();
    fireEvent.click(await screen.findByRole("button", { name: "Save as defaults" }));

    await waitFor(() => expect(show).toHaveBeenCalled());
    const shown = show.mock.calls[show.mock.calls.length - 1][0] as
      { title?: string; message: string; color: string };
    expect(put).toHaveBeenCalled();
    expect(shown.title).toBe("Saved as defaults");
    expect(shown.color).toBe("teal");
    expect(shown.message).not.toContain("Save failed");
  });
});
