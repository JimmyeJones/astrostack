import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CalibrationView } from "./Calibration";
import * as client from "../api/client";
import type { CalibrationMaster } from "../api/client";

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
});
