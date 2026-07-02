import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TargetView } from "./Target";
import * as client from "../api/client";
import type { Frame, Target } from "../api/client";

function mkFrame(id: number, overrides: Partial<Frame> = {}): Frame {
  return {
    id, name: `f${id}.fits`, timestamp_utc: "2026-01-01T00:00:00",
    exposure_s: 30, gain: 100, width_px: 480, height_px: 320,
    bayer_pattern: "RGGB", solved: true, ra_center_deg: 10, dec_center_deg: 20,
    ra_hint_deg: null, dec_hint_deg: null, fwhm_px: 2.5, star_count: 100,
    sky_adu_median: 500, eccentricity_median: 0.4, streak_detected: false,
    accept: true, reject_reason: null, user_override: false, ...overrides,
  };
}

function mkTarget(overrides: Partial<Target> = {}): Target {
  return {
    safe_name: "M_42", name: "M42", ra_deg: 10, dec_deg: 20,
    n_frames: 3, n_frames_accepted: 3, total_exposure_s: 90,
    last_activity_utc: "2026-01-01T00:00:00", has_preview: false,
    notes: null, tags: [], ...overrides,
  };
}

function renderTarget() {
  const qc = new QueryClient();
  return render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/targets/M_42"]}>
          <Routes>
            <Route path="/targets/:safe" element={<TargetView />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("TargetView streaked badge", () => {
  it("shows a streaked-frame count for accepted frames carrying a trail", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { streak_detected: true }),
      mkFrame(2, { streak_detected: true }),
      // a rejected streaked frame should not count
      mkFrame(3, { streak_detected: true, accept: false }),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("2 streaked")).toBeInTheDocument());
  });

  it("rejects all streaked frames in one gesture from the badge action", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { streak_detected: true }),
      mkFrame(2, { streak_detected: true }),
    ]);
    const bulk = vi
      .spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 2, changed_ids: [1, 2] });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderTarget();

    const btn = await screen.findByRole("button", {
      name: "Reject all streaked frames",
    });
    btn.click();

    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", { action: "reject_streaked" }));
  });

  it("omits the badge when no accepted frame carries a trail", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1), mkFrame(2),
    ]);

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("3/3 accepted")).toBeInTheDocument());
    expect(screen.queryByText(/streaked/)).not.toBeInTheDocument();
  });
});

describe("TargetView reject breakdown + undo", () => {
  it("shows a rejected-count badge with a why breakdown", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(
      mkTarget({ n_frames: 5, n_frames_accepted: 3 }),
    );
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([mkFrame(1)]);
    const summary = vi
      .spyOn(client.api, "rejectSummary")
      .mockResolvedValue({ counts: { "qc:fwhm": 1, user: 1 }, total: 2 });

    renderTarget();

    await waitFor(() =>
      expect(screen.getByText("2 rejected")).toBeInTheDocument());
    expect(summary).toHaveBeenCalledWith("M_42");
  });

  it("offers Undo after a bulk reject and re-accepts exactly those ids", async () => {
    vi.spyOn(client.api, "getTarget").mockResolvedValue(mkTarget());
    vi.spyOn(client.api, "listStackRuns").mockResolvedValue([]);
    vi.spyOn(client.api, "listFrames").mockResolvedValue([
      mkFrame(1, { streak_detected: true }),
      mkFrame(2, { streak_detected: true }),
    ]);
    const bulk = vi
      .spyOn(client.api, "bulkFrames")
      .mockResolvedValue({ changed: 2, changed_ids: [1, 2] });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    renderTarget();

    const reject = await screen.findByRole("button", {
      name: "Reject all streaked frames",
    });
    reject.click();

    const undo = await screen.findByRole("button", {
      name: "Undo last bulk reject",
    });
    undo.click();

    await waitFor(() =>
      expect(bulk).toHaveBeenCalledWith("M_42", { action: "accept", ids: [1, 2] }));
  });
});
