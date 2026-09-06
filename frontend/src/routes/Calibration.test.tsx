import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

// The "you already have darks" offer lives on this page but is its own query and
// its own test file; stub it empty everywhere here so it self-hides and these
// tests stay about the master list.
beforeEach(() => {
  vi.spyOn(client.api, "calibrationIncoming").mockResolvedValue({
    incoming_dir: "/data/incoming", folders: [],
  });
  // Same reasoning for the sensor-defect census: its own query, its own tests
  // below. Empty here so the master rows stay about whatever each test is
  // pinning; a test that wants a census re-mocks it.
  vi.spyOn(client.api, "calibrationDefects").mockResolvedValue({ masters: [], repair: null });
});

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

  it("says how many photosites this dark shows as broken", async () => {
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([mk({})]);
    vi.spyOn(client.api, "calibrationCoverage").mockResolvedValue(NO_COVERAGE);
    vi.spyOn(client.api, "calibrationDefects").mockResolvedValue({
      masters: [{
        id: 1, n_defects: 1204, n_pixels: 2073600, fraction: 1204 / 2073600,
        refused: false, measurable: true,
        note: {
          severity: "ok",
          message: "1,204 hot or dead pixels (0.058%)",
          detail: "…Repair hot/dead pixels from the dark…",
        },
      }],
      repair: null,
    });
    renderView();

    await waitFor(() =>
      expect(screen.getByText("1,204 hot or dead pixels (0.058%)"))
        .toBeInTheDocument());
  });

  it("says nothing about defects on a master the server had no note for", async () => {
    // Two silences share this path and both must hold: a clean sensor (a row
    // with `note: null`) and a master the census skipped entirely (a flat, or
    // one that couldn't be read — no row at all).
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([
      mk({}), mk({ id: 2, name: "Flat", kind: "flat" }),
    ]);
    vi.spyOn(client.api, "calibrationCoverage").mockResolvedValue(NO_COVERAGE);
    vi.spyOn(client.api, "calibrationDefects").mockResolvedValue({
      masters: [{
        id: 1, n_defects: 0, n_pixels: 2073600, fraction: 0,
        refused: false, measurable: true, note: null,
      }],
      repair: null,
    });
    renderView();

    await waitFor(() => expect(screen.getByText("Flat")).toBeInTheDocument());
    expect(screen.queryByText(/hot or dead pixels/)).not.toBeInTheDocument();
  });

  it("warns when a master's defect count is too big to repair from", async () => {
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([mk({})]);
    vi.spyOn(client.api, "calibrationCoverage").mockResolvedValue(NO_COVERAGE);
    vi.spyOn(client.api, "calibrationDefects").mockResolvedValue({
      masters: [{
        id: 1, n_defects: 960, n_pixels: 19200, fraction: 0.05,
        refused: true, measurable: true,
        note: {
          severity: "warn",
          message: "Too many pixels read as broken to repair from this one",
          detail: "960 pixels (5.00% of the sensor) look broken…",
        },
      }],
      repair: null,
    });
    renderView();

    await waitFor(() =>
      expect(screen.getByText(/Too many pixels read as broken/))
        .toBeInTheDocument());
  });
  // ---- the one-click repair (the action beside the measurement) ------------
  //
  // The rows say how many photosites are broken; without this the only way to
  // act on that is to find a named checkbox inside the Stack form's advanced
  // group, once per stack, and never at all on the hands-off path.

  const censusOf = (repair: client.CalibrationDefects["repair"]) => ({
    masters: [{
      id: 1, n_defects: 1204, n_pixels: 2073600, fraction: 1204 / 2073600,
      refused: false, measurable: true,
      note: {
        severity: "ok" as const,
        message: "1,204 hot or dead pixels (0.058%)",
        detail: "\u2026",
      },
    }],
    repair,
  });

  it("offers one click that repairs the broken pixels on every future stack",
    async () => {
      vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([mk({})]);
      vi.spyOn(client.api, "calibrationCoverage").mockResolvedValue(NO_COVERAGE);
      vi.spyOn(client.api, "calibrationDefects").mockResolvedValue(censusOf({
        state: "off",
        message: "Repair these on every stack from now on",
        detail: "Turns on the repair for every stack \u2026",
        action: "Repair them",
      }));
      const set = vi.spyOn(client.api, "setDefectRepair")
        .mockResolvedValue({ enabled: true });
      renderView();

      await waitFor(() =>
        expect(screen.getByText("Repair these on every stack from now on"))
          .toBeInTheDocument());
      fireEvent.click(screen.getByRole("button", { name: "Repair them" }));

      await waitFor(() => expect(set).toHaveBeenCalledWith(true));
    });

  it("turns the same control into the way back off once it is on", async () => {
    // Reversible from where it was switched on \u2014 the user must never have to
    // go hunting in Settings to undo a click they made here.
    vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([mk({})]);
    vi.spyOn(client.api, "calibrationCoverage").mockResolvedValue(NO_COVERAGE);
    vi.spyOn(client.api, "calibrationDefects").mockResolvedValue(censusOf({
      state: "on",
      message: "Broken pixels are repaired on every stack",
      detail: "Every stack from now on \u2026",
      action: "Turn off",
    }));
    const set = vi.spyOn(client.api, "setDefectRepair")
      .mockResolvedValue({ enabled: false });
    renderView();

    await waitFor(() =>
      expect(screen.getByText("Broken pixels are repaired on every stack"))
        .toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Turn off" }));

    await waitFor(() => expect(set).toHaveBeenCalledWith(false));
  });

  it("offers nothing when the server says there is nothing repairable",
    async () => {
      // A clean sensor and a refused map both arrive as `repair: null`, and the
      // whole control is absent rather than shown-and-disabled.
      vi.spyOn(client.api, "listCalibrationMasters").mockResolvedValue([mk({})]);
      vi.spyOn(client.api, "calibrationCoverage").mockResolvedValue(NO_COVERAGE);
      vi.spyOn(client.api, "calibrationDefects").mockResolvedValue(censusOf(null));
      renderView();

      await waitFor(() =>
        expect(screen.getByText("1,204 hot or dead pixels (0.058%)"))
          .toBeInTheDocument());
      expect(screen.queryByRole("button", { name: /Repair them|Turn off/ }))
        .not.toBeInTheDocument();
    });
});
