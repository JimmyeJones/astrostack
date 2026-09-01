import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CaptureQuietNote } from "./CaptureQuietNote";
import * as client from "../api/client";
import type { LiveSession } from "../api/client";

function live(over: Partial<LiveSession> = {}): LiveSession {
  return {
    active: false,
    n_frames: 143,
    n_kept: 130,
    n_set_aside: 13,
    kept_exposure_s: 1300,
    session_exposure_s: 1430,
    total_kept_exposure_s: 9000,
    start_utc: "2026-07-08T21:00:00Z",
    latest_utc: "2026-07-08T22:00:00Z",
    minutes_since_latest: 72,
    conditions: {
      verdict: "good", n_recent: 20, n_recent_kept: 19,
      median_fwhm_px: 3.2, recent_buckets: {},
    },
    reject_buckets: {},
    newest_kept_frame_id: 7,
    goal_exposure_s: null,
    quiet: true,
    typical_gap_minutes: 0.5,
    quiet_after_minutes: 45,
    ...over,
  };
}

function renderNote() {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <CaptureQuietNote safe="m_42" />
        </QueryClientProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

afterEach(() => vi.restoreAllMocks());

describe("CaptureQuietNote", () => {
  it("says how long it has been quiet, and what the cadence was", async () => {
    vi.spyOn(client.api, "liveSession").mockResolvedValue(live());
    renderNote();

    await waitFor(() =>
      expect(screen.getByTestId("capture-quiet-note")).toBeInTheDocument());
    expect(screen.getByText(/getting a sub about every 30 s/)).toBeInTheDocument();
    expect(screen.getByText(/nothing arrived for 1\.2 h/)).toBeInTheDocument();
    // What it got so far, so the reader knows the night isn't a write-off.
    expect(screen.getByText(/143 subs \(22 min kept\)/)).toBeInTheDocument();
  });

  it("does not scold someone who simply finished for the night", async () => {
    vi.spyOn(client.api, "liveSession").mockResolvedValue(live());
    renderNote();
    await waitFor(() =>
      expect(screen.getByTestId("capture-quiet-note")).toBeInTheDocument());
    expect(screen.getByText(/If you finished for the night, nothing is wrong/))
      .toBeInTheDocument();
  });

  it("stays silent while the session is still filling up", async () => {
    const spy = vi.spyOn(client.api, "liveSession")
      .mockResolvedValue(live({ active: true, quiet: false, minutes_since_latest: 2 }));
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("capture-quiet-note")).toBeNull();
  });

  it("stays silent on an older backend that has no quiet verdict", async () => {
    const { quiet: _q, ...older } = live();
    const spy = vi.spyOn(client.api, "liveSession")
      .mockResolvedValue(older as LiveSession);
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("capture-quiet-note")).toBeNull();
  });

  it("stays silent when there is no session at all, or the fetch fails", async () => {
    const spy = vi.spyOn(client.api, "liveSession").mockResolvedValue(null);
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByTestId("capture-quiet-note")).toBeNull();

    spy.mockRejectedValue(new Error("404"));
    renderNote();
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2));
    expect(screen.queryByTestId("capture-quiet-note")).toBeNull();
  });
});
