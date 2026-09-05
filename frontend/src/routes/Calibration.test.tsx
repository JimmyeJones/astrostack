import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CalibrationView } from "./Calibration";
import * as client from "../api/client";
import type { CalibrationCoverage, CalibrationMaster } from "../api/client";

const NO_COVERAGE: CalibrationCoverage = { n_targets: 0, masters: [], uncovered: [] };

function mk(over: Partial<CalibrationMaster>): CalibrationMaster {
  return {
    id: 1, name: "Dark 30s", kind: "dark", filename: "dark_1.fits",
    n_frames: 20, method: "median", exposure_s: 30, gain: 80,
    sensor_temp_c: -5, bayer_pattern: "RGGB", width_px: 1080, height_px: 1920,
    created_utc: "2026-01-01T00:00:00Z", exists: true, ...over,
  };
}

function renderView() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter><CalibrationView /></MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("CalibrationView", () => {
  it("lists masters and submits a build", async () => {
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([mk({})]);
    vi.spyOn(client.api, "calibrationCoverage").mockResolvedValue(NO_COVERAGE);
    const build = vi.spyOn(client.api, "buildCalibrationMaster")
      .mockResolvedValue({ job_id: "j1" });
    renderView();

    await waitFor(() => expect(screen.getByText("Dark 30s")).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText("/data/incoming/darks"),
      { target: { value: "/data/darks" } });
    fireEvent.click(screen.getByRole("button", { name: /Build/ }));

    await waitFor(() => expect(build).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "dark", source_dir: "/data/darks" })));
  });

  it("gives the icon-only delete button an accessible name", async () => {
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([mk({})]);
    vi.spyOn(client.api, "calibrationCoverage").mockResolvedValue(NO_COVERAGE);
    renderView();
    await waitFor(() => expect(screen.getByText("Dark 30s")).toBeInTheDocument());
    // Icon-only ActionIcon must be reachable by an accessible name (aria-label),
    // not just a hover tooltip — otherwise it's invisible to screen readers.
    expect(
      screen.getByRole("button", { name: /Delete master Dark 30s/ }),
    ).toBeInTheDocument();
  });

  it("tells the user which of their targets each master actually covers", async () => {
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([mk({})]);
    vi.spyOn(client.api, "calibrationCoverage").mockResolvedValue({
      n_targets: 6,
      masters: [{
        id: 1, name: "Dark 30s", kind: "dark", n_covered: 4,
        covered: ["M 42", "M 31", "M 45", "NGC 7000"], missed: ["M 13", "M 51"],
      }],
      uncovered: ["M 13", "M 51"],
    });
    renderView();

    await waitFor(() =>
      expect(screen.getByText("Covers 4 of your 6 targets")).toBeInTheDocument());
    // And the gap the user would otherwise only discover after an uncalibrated
    // result, with a plain next step.
    await waitFor(() =>
      expect(
        screen.getByText(/2 of your 6 targets have no matching master/),
      ).toBeInTheDocument());
  });

  it("stays quiet about coverage when every target is already covered", async () => {
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([mk({})]);
    vi.spyOn(client.api, "calibrationCoverage").mockResolvedValue({
      n_targets: 2,
      masters: [{
        id: 1, name: "Dark 30s", kind: "dark", n_covered: 2,
        covered: ["M 42", "M 31"], missed: [],
      }],
      uncovered: [],
    });
    renderView();

    await waitFor(() =>
      expect(screen.getByText("Covers all 2 of your targets")).toBeInTheDocument());
    expect(screen.queryByText(/no matching master/)).not.toBeInTheDocument();
  });

  it("shows what the master's own frames said they were", async () => {
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([mk({
      header_kinds: { light: 40 },
      header_note: {
        severity: "warn",
        message: "Every frame here says something else: 40 say they are light "
          + "frames (your subs). This is not a dark master — delete it and point "
          + "the build at a folder of dark frames.",
      },
    })]);
    vi.spyOn(client.api, "calibrationCoverage").mockResolvedValue(NO_COVERAGE);
    renderView();

    await waitFor(() =>
      expect(screen.getByText(/40 say they are light frames \(your subs\)/))
        .toBeInTheDocument());
  });

  it("says nothing when the frames never said what they were", async () => {
    // A camera that doesn't write IMAGETYP is unknown, not suspect — and every
    // master built before the check existed carries no tally at all.
    vi.spyOn(client.api, "listCalibrationMasters")
      .mockResolvedValue([mk({ header_note: null })]);
    vi.spyOn(client.api, "calibrationCoverage").mockResolvedValue(NO_COVERAGE);
    renderView();

    await waitFor(() => expect(screen.getByText("Dark 30s")).toBeInTheDocument());
    expect(screen.queryByText(/say they are/)).not.toBeInTheDocument();
  });
});
